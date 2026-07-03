import hashlib
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.email_outbox import EmailOutbox
from app.models.membership import Membership
from app.models.notice_user_acknowledgement import NoticeUserAcknowledgement
from app.models.privacy_notice import PrivacyNotice
from app.models.user import User
from app.services.audit_service import AuditService
from app.core.validation import validate_choice

ALLOWED_NOTICE_STATUS = {"draft", "published", "archived"}


class NoticeService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def hash_content(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _next_version(self, org_id: uuid.UUID, language: str) -> str:
        rows = self.db.execute(
            select(PrivacyNotice.version).where(
                PrivacyNotice.organization_id == org_id,
                PrivacyNotice.language == language,
            )
        ).scalars().all()
        max_v = 0
        for v in rows:
            try:
                max_v = max(max_v, int(v))
            except Exception:
                continue
        return str(max_v + 1)

    def _require_notice(self, org_id: uuid.UUID, notice_id: uuid.UUID) -> PrivacyNotice:
        row = self.db.execute(
            select(PrivacyNotice).where(
                PrivacyNotice.organization_id == org_id,
                PrivacyNotice.id == notice_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Privacy notice not found")
        return row

    def _org_users(self, org_id: uuid.UUID) -> list[User]:
        rows = self.db.execute(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(
                Membership.organization_id == org_id,
                Membership.status == "active",
                User.is_active.is_(True),
                User.status == "active",
                User.email.is_not(None),
            )
        ).scalars().all()
        dedup: dict[uuid.UUID, User] = {row.id: row for row in rows}
        return list(dedup.values())

    def _queue_notice_published_notifications(self, org_id: uuid.UUID, notice: PrivacyNotice, actor_user_id: uuid.UUID) -> None:
        now = self.utcnow()
        users = self._org_users(org_id)
        for user in users:
            outbox = EmailOutbox(
                organization_id=org_id,
                template_id=None,
                event_type="notice.published",
                recipient_email=user.email,
                recipient_user_id=user.id,
                subject=f"Updated privacy notice: {notice.title}",
                body_text=(
                    f"A new privacy notice version ({notice.version}) has been published for language {notice.language}. "
                    f"Please review and acknowledge it in CompliVibe."
                ),
                body_html=(
                    f"<p>A new privacy notice version ({notice.version}) has been published for language {notice.language}. "
                    "Please review and acknowledge it in CompliVibe.</p>"
                ),
                status="pending",
                priority="normal",
                scheduled_at=None,
                queued_at=now,
                sent_at=None,
                failed_at=None,
                cancelled_at=None,
                locked_at=None,
                locked_by=None,
                lock_expires_at=None,
                last_attempt_at=None,
                next_attempt_at=None,
                dead_lettered_at=None,
                attempt_count=0,
                max_attempts=3,
                last_error=None,
                provider=None,
                provider_message_id=None,
                metadata_json={"source": "privacy_notice", "notice_id": str(notice.id)},
                worker_metadata_json=None,
                created_by_user_id=actor_user_id,
            )
            self.db.add(outbox)
        self.db.flush()

    def create_notice(self, org_id: uuid.UUID, data, created_by: uuid.UUID) -> PrivacyNotice:
        payload = data.model_dump()
        now = self.utcnow()
        language = payload.get("language") or "en"

        row = PrivacyNotice(
            organization_id=org_id,
            title=payload["title"],
            version=self._next_version(org_id, language),
            content=payload["content"],
            content_hash=self.hash_content(payload["content"]),
            language=language,
            status="draft",
            published_at=None,
            published_by=None,
            effective_date=payload.get("effective_date"),
            frameworks=payload.get("frameworks") or [],
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="notice.created",
            entity_type="privacy_notice",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={"title": row.title, "version": row.version, "language": row.language, "status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def get_notice(self, org_id: uuid.UUID, notice_id: uuid.UUID) -> PrivacyNotice:
        return self._require_notice(org_id, notice_id)

    def get_active_notice(self, org_id: uuid.UUID, language: str = "en") -> PrivacyNotice | None:
        return self.db.execute(
            select(PrivacyNotice).where(
                PrivacyNotice.organization_id == org_id,
                PrivacyNotice.language == language,
                PrivacyNotice.status == "published",
            )
        ).scalar_one_or_none()

    def list_notices(self, org_id: uuid.UUID, status_filter: str | None = None, language: str | None = None) -> list[PrivacyNotice]:
        stmt = select(PrivacyNotice).where(PrivacyNotice.organization_id == org_id)
        if status_filter is not None:
            status_filter = validate_choice(status_filter, ALLOWED_NOTICE_STATUS, "status")
            stmt = stmt.where(PrivacyNotice.status == status_filter)
        if language is not None:
            stmt = stmt.where(PrivacyNotice.language == language)
        return self.db.execute(stmt.order_by(PrivacyNotice.created_at.desc())).scalars().all()

    def update_notice(self, org_id: uuid.UUID, notice_id: uuid.UUID, data, actor_user_id: uuid.UUID) -> PrivacyNotice:
        row = self._require_notice(org_id, notice_id)
        if row.status != "draft":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only draft notices can be updated")

        payload = data.model_dump(exclude_unset=True)
        for key, value in payload.items():
            setattr(row, key, value)

        row.content_hash = self.hash_content(row.content)
        row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="notice.updated",
            entity_type="privacy_notice",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={"title": row.title, "version": row.version, "language": row.language, "status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def publish_notice(self, org_id: uuid.UUID, notice_id: uuid.UUID, user_id: uuid.UUID) -> PrivacyNotice:
        row = self._require_notice(org_id, notice_id)
        if row.status != "draft":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only draft notices can be published")

        now = self.utcnow()
        current_published = self.db.execute(
            select(PrivacyNotice).where(
                PrivacyNotice.organization_id == org_id,
                PrivacyNotice.language == row.language,
                PrivacyNotice.status == "published",
                PrivacyNotice.id != row.id,
            )
        ).scalar_one_or_none()
        if current_published is not None:
            current_published.status = "archived"
            current_published.updated_at = now

        row.status = "published"
        row.published_at = now
        row.published_by = user_id
        row.updated_at = now
        self.db.flush()

        self._queue_notice_published_notifications(org_id, row, user_id)

        AuditService(self.db).write_audit_log(
            action="notice.published",
            entity_type="privacy_notice",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"version": row.version, "language": row.language, "status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def acknowledge_notice(
        self,
        org_id: uuid.UUID,
        notice_id: uuid.UUID,
        user_id: uuid.UUID,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> NoticeUserAcknowledgement:
        self._require_notice(org_id, notice_id)

        row = self.db.execute(
            select(NoticeUserAcknowledgement).where(
                NoticeUserAcknowledgement.organization_id == org_id,
                NoticeUserAcknowledgement.notice_id == notice_id,
                NoticeUserAcknowledgement.user_id == user_id,
            )
        ).scalar_one_or_none()

        now = self.utcnow()
        if row is None:
            row = NoticeUserAcknowledgement(
                organization_id=org_id,
                notice_id=notice_id,
                user_id=user_id,
                acknowledged_at=now,
                ip_address=ip,
                user_agent=user_agent,
            )
            self.db.add(row)
        else:
            row.acknowledged_at = now
            row.ip_address = ip
            row.user_agent = user_agent

        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="notice.acknowledged",
            entity_type="privacy_notice",
            entity_id=notice_id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"notice_id": str(notice_id), "acknowledged_at": row.acknowledged_at.isoformat()},
            metadata_json={"source": "api"},
        )
        return row

    def get_acknowledgement_status(self, org_id: uuid.UUID, notice_id: uuid.UUID) -> dict:
        self._require_notice(org_id, notice_id)

        total_users = int(
            self.db.execute(
                select(func.count(func.distinct(Membership.user_id))).where(
                    Membership.organization_id == org_id,
                    Membership.status == "active",
                )
            ).scalar_one()
            or 0
        )

        acknowledged_count = int(
            self.db.execute(
                select(func.count(NoticeUserAcknowledgement.id)).where(
                    NoticeUserAcknowledgement.organization_id == org_id,
                    NoticeUserAcknowledgement.notice_id == notice_id,
                )
            ).scalar_one()
            or 0
        )

        pending = max(total_users - acknowledged_count, 0)
        rate = (acknowledged_count / total_users * 100) if total_users > 0 else 0.0

        return {
            "total_users": total_users,
            "acknowledged_count": acknowledged_count,
            "pending_count": pending,
            "acknowledgement_rate_pct": round(rate, 2),
        }
