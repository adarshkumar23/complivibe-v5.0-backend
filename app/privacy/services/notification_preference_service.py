import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user_notification_preference import UserNotificationPreference
from app.services.audit_service import AuditService

KNOWN_NOTIFICATION_TYPES = [
    "task_assigned",
    "evidence_expiring",
    "deadline_approaching",
    "audit_finding_raised",
    "new_obligation_activated",
    "sla_breach",
    "dsr_received",
    "consent_withdrawn",
    "risk_escalated",
    "breach_notification_due",
    "digest_daily",
    "digest_weekly",
]

ALLOWED_CHANNELS = {"email", "in_app", "none"}
ALLOWED_SEVERITIES = {"critical", "high", "medium", "low"}
SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}


class NotificationPreferenceService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def get_or_create_preferences(self, org_id: uuid.UUID, user_id: uuid.UUID) -> list[UserNotificationPreference]:
        now = self.utcnow()
        for notification_type in KNOWN_NOTIFICATION_TYPES:
            existing = self.db.execute(
                select(UserNotificationPreference).where(
                    UserNotificationPreference.organization_id == org_id,
                    UserNotificationPreference.user_id == user_id,
                    UserNotificationPreference.notification_type == notification_type,
                )
            ).scalar_one_or_none()
            if existing is None:
                self.db.add(
                    UserNotificationPreference(
                        organization_id=org_id,
                        user_id=user_id,
                        notification_type=notification_type,
                        channel="email",
                        min_severity=None,
                        is_enabled=True,
                        created_at=now,
                        updated_at=now,
                    )
                )
        self.db.flush()
        return self.db.execute(
            select(UserNotificationPreference)
            .where(
                UserNotificationPreference.organization_id == org_id,
                UserNotificationPreference.user_id == user_id,
            )
            .order_by(UserNotificationPreference.notification_type.asc())
        ).scalars().all()

    def get_preference(self, org_id: uuid.UUID, user_id: uuid.UUID, notification_type: str) -> UserNotificationPreference | None:
        return self.db.execute(
            select(UserNotificationPreference).where(
                UserNotificationPreference.organization_id == org_id,
                UserNotificationPreference.user_id == user_id,
                UserNotificationPreference.notification_type == notification_type,
            )
        ).scalar_one_or_none()

    def update_preference(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        notification_type: str,
        channel: str,
        is_enabled: bool,
        min_severity: str | None,
    ) -> UserNotificationPreference:
        if channel not in ALLOWED_CHANNELS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid channel")
        if min_severity is not None and min_severity not in ALLOWED_SEVERITIES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid min_severity")

        self.get_or_create_preferences(org_id, user_id)
        row = self.get_preference(org_id, user_id, notification_type)
        if row is None:
            now = self.utcnow()
            row = UserNotificationPreference(
                organization_id=org_id,
                user_id=user_id,
                notification_type=notification_type,
                channel=channel,
                min_severity=min_severity,
                is_enabled=False if channel == "none" else bool(is_enabled),
                created_at=now,
                updated_at=now,
            )
            self.db.add(row)
        else:
            row.channel = channel
            row.is_enabled = False if channel == "none" else bool(is_enabled)
            row.min_severity = min_severity
            row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="notification_preference.updated",
            entity_type="user_notification_preference",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={
                "notification_type": row.notification_type,
                "channel": row.channel,
                "is_enabled": row.is_enabled,
                "min_severity": row.min_severity,
            },
            metadata_json={"source": "api"},
        )
        return row

    def bulk_update_preferences(self, org_id: uuid.UUID, user_id: uuid.UUID, updates: list[dict]) -> list[UserNotificationPreference]:
        rows: list[UserNotificationPreference] = []
        for item in updates:
            rows.append(
                self.update_preference(
                    org_id=org_id,
                    user_id=user_id,
                    notification_type=str(item["notification_type"]),
                    channel=str(item["channel"]),
                    is_enabled=bool(item.get("is_enabled", True)),
                    min_severity=item.get("min_severity"),
                )
            )
        return rows

    def should_notify(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        notification_type: str,
        severity: str | None = None,
    ) -> bool:
        row = self.get_preference(org_id, user_id, notification_type)
        if row is None:
            self.get_or_create_preferences(org_id, user_id)
            row = self.get_preference(org_id, user_id, notification_type)

        if row is None:
            return True
        if row.channel == "none":
            return False
        if not row.is_enabled:
            return False

        if row.min_severity is None:
            return True
        if severity is None:
            return True
        if severity not in SEVERITY_RANK:
            return True

        return SEVERITY_RANK[severity] >= SEVERITY_RANK[row.min_severity]
