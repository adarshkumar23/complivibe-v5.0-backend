import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.email_outbox import EmailOutbox
from app.models.escalation_event import EscalationEvent
from app.models.escalation_policy import EscalationPolicy
from app.models.issue import Issue
from app.models.issue_sla_tracking import IssueSLATracking
from app.models.membership import Membership
from app.models.user import User
from app.services.audit_service import AuditService


class EscalationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _ensure_active_member(self, org_id: uuid.UUID, user_id: uuid.UUID, field_name: str) -> None:
        membership = self.db.execute(
            select(Membership).where(
                Membership.organization_id == org_id,
                Membership.user_id == user_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{field_name} must be an active organization member")

        user = self.db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if user is None or not user.is_active or user.status != "active":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{field_name} must be an active organization member")

    def _validate_policy_condition(self, *, condition_type: str, condition_value: dict) -> None:
        payload = condition_value or {}
        if condition_type == "time_in_state":
            hours = payload.get("hours")
            if not isinstance(hours, int) or hours <= 0:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="condition_value.hours must be a positive integer")
        elif condition_type == "severity_threshold":
            severity = payload.get("severity")
            if severity not in {"critical", "high", "medium", "low"}:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="condition_value.severity must be one of critical, high, medium, low")
        elif condition_type == "sla_breach":
            if payload not in ({}, None):
                # Allow extras but enforce object type.
                if not isinstance(payload, dict):
                    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="condition_value must be a JSON object")

    def create_policy(self, org_id: uuid.UUID, data, created_by: uuid.UUID) -> EscalationPolicy:
        self._ensure_active_member(org_id, data.escalate_to_user_id, "escalate_to_user_id")
        self._validate_policy_condition(condition_type=data.condition_type, condition_value=dict(data.condition_value or {}))

        row = EscalationPolicy(
            organization_id=org_id,
            name=data.name,
            entity_type=data.entity_type,
            condition_type=data.condition_type,
            condition_value=dict(data.condition_value or {}),
            escalate_to_user_id=data.escalate_to_user_id,
            notification_message_template=data.notification_message_template,
            is_active=True,
            created_by=created_by,
            deleted_at=None,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="escalation_policy.created",
            entity_type="escalation_policy",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={"entity_type": row.entity_type, "condition_type": row.condition_type, "is_active": row.is_active},
            metadata_json={"source": "api"},
        )
        return row

    def get_policy(self, org_id: uuid.UUID, policy_id: uuid.UUID) -> EscalationPolicy:
        row = self.db.execute(
            select(EscalationPolicy).where(
                EscalationPolicy.id == policy_id,
                EscalationPolicy.organization_id == org_id,
                EscalationPolicy.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Escalation policy not found")
        return row

    def list_policies(self, org_id: uuid.UUID, *, entity_type: str | None = None, is_active: bool | None = None) -> list[EscalationPolicy]:
        stmt = select(EscalationPolicy).where(
            EscalationPolicy.organization_id == org_id,
            EscalationPolicy.deleted_at.is_(None),
        )
        if entity_type is not None:
            stmt = stmt.where(EscalationPolicy.entity_type == entity_type)
        if is_active is not None:
            stmt = stmt.where(EscalationPolicy.is_active.is_(is_active))

        return self.db.execute(stmt.order_by(EscalationPolicy.created_at.desc())).scalars().all()

    def update_policy(self, org_id: uuid.UUID, policy_id: uuid.UUID, data, actor_user_id: uuid.UUID | None = None) -> EscalationPolicy:
        row = self.get_policy(org_id, policy_id)
        updates = data.model_dump(exclude_unset=True)
        if "escalate_to_user_id" in updates and updates["escalate_to_user_id"] is not None:
            self._ensure_active_member(org_id, updates["escalate_to_user_id"], "escalate_to_user_id")

        merged_condition = dict(row.condition_value or {})
        if "condition_value" in updates and updates["condition_value"] is not None:
            merged_condition = dict(updates["condition_value"])
        self._validate_policy_condition(condition_type=row.condition_type, condition_value=merged_condition)

        before = {
            "name": row.name,
            "condition_value": dict(row.condition_value or {}),
            "escalate_to_user_id": str(row.escalate_to_user_id),
            "notification_message_template": row.notification_message_template,
            "is_active": row.is_active,
        }

        for field, value in updates.items():
            setattr(row, field, value)

        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="escalation_policy.updated",
            entity_type="escalation_policy",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json={
                "name": row.name,
                "condition_value": dict(row.condition_value or {}),
                "escalate_to_user_id": str(row.escalate_to_user_id),
                "notification_message_template": row.notification_message_template,
                "is_active": row.is_active,
            },
            metadata_json={"source": "api"},
        )
        return row

    def deactivate_policy(self, org_id: uuid.UUID, policy_id: uuid.UUID, user_id: uuid.UUID) -> EscalationPolicy:
        row = self.get_policy(org_id, policy_id)
        row.is_active = False
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="escalation_policy.deactivated",
            entity_type="escalation_policy",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"is_active": row.is_active},
            metadata_json={"source": "api"},
        )
        return row

    def soft_delete_policy(self, org_id: uuid.UUID, policy_id: uuid.UUID, user_id: uuid.UUID) -> EscalationPolicy:
        row = self.get_policy(org_id, policy_id)
        if row.is_active:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only deactivated escalation policies can be deleted")
        row.deleted_at = self.utcnow()
        self.db.flush()
        return row

    def _issue_candidates_for_policy(self, policy: EscalationPolicy) -> list[Issue]:
        now = self.utcnow()
        if policy.condition_type == "time_in_state":
            hours = int((policy.condition_value or {}).get("hours", 0))
            if hours <= 0:
                return []
            cutoff = now - timedelta(hours=hours)
            return self.db.execute(
                select(Issue).where(
                    Issue.organization_id == policy.organization_id,
                    Issue.deleted_at.is_(None),
                    Issue.status.notin_(["resolved", "closed"]),
                    Issue.updated_at < cutoff,
                )
            ).scalars().all()

        if policy.condition_type == "sla_breach":
            rows = self.db.execute(
                select(Issue)
                .join(IssueSLATracking, IssueSLATracking.issue_id == Issue.id)
                .where(
                    Issue.organization_id == policy.organization_id,
                    IssueSLATracking.organization_id == policy.organization_id,
                    Issue.deleted_at.is_(None),
                    Issue.status.notin_(["resolved", "closed"]),
                    or_(IssueSLATracking.response_breached.is_(True), IssueSLATracking.resolution_breached.is_(True)),
                )
            ).scalars().all()
            return rows

        if policy.condition_type == "severity_threshold":
            severity = (policy.condition_value or {}).get("severity")
            if severity not in {"critical", "high", "medium", "low"}:
                return []
            cutoff = now - timedelta(hours=1)
            return self.db.execute(
                select(Issue).where(
                    Issue.organization_id == policy.organization_id,
                    Issue.deleted_at.is_(None),
                    Issue.status.notin_(["resolved", "closed"]),
                    Issue.severity == severity,
                    Issue.created_at < cutoff,
                )
            ).scalars().all()

        return []

    def _resolve_candidates(self, policy: EscalationPolicy) -> list[tuple[str, uuid.UUID]]:
        if policy.entity_type == "issue":
            return [("issue", row.id) for row in self._issue_candidates_for_policy(policy)]
        return []

    def _is_idempotent_skip(self, policy_id: uuid.UUID, entity_id: uuid.UUID, now: datetime) -> bool:
        window_start = now - timedelta(hours=24)
        existing = self.db.execute(
            select(EscalationEvent.id).where(
                EscalationEvent.policy_id == policy_id,
                EscalationEvent.entity_id == entity_id,
                EscalationEvent.escalated_at >= window_start,
            )
        ).first()
        return existing is not None

    def _queue_notification(self, *, org_id: uuid.UUID, escalated_to: uuid.UUID, subject: str, body: str) -> tuple[bool, datetime | None]:
        user = self.db.execute(select(User).where(User.id == escalated_to)).scalar_one_or_none()
        if user is None or not user.email:
            return False, None

        now = self.utcnow()
        self.db.add(
            EmailOutbox(
                organization_id=org_id,
                template_id=None,
                event_type="escalation.policy_triggered",
                recipient_email=user.email,
                recipient_user_id=user.id,
                subject=subject,
                body_text=body,
                body_html=None,
                status="pending",
                priority="high",
                scheduled_at=None,
                queued_at=now,
                attempt_count=0,
                max_attempts=3,
                metadata_json={"source": "escalation_policy"},
                created_by_user_id=None,
            )
        )
        return True, now

    def evaluate_policies(self, org_id: uuid.UUID | None = None) -> dict[str, int]:
        now = self.utcnow()
        stmt = select(EscalationPolicy).where(
            EscalationPolicy.is_active.is_(True),
            EscalationPolicy.deleted_at.is_(None),
        )
        if org_id is not None:
            stmt = stmt.where(EscalationPolicy.organization_id == org_id)

        policies = self.db.execute(stmt.order_by(EscalationPolicy.created_at.asc())).scalars().all()

        policies_evaluated = 0
        escalations_fired = 0
        skipped_idempotent = 0

        for policy in policies:
            policies_evaluated += 1
            candidates = self._resolve_candidates(policy)
            for entity_type, entity_id in candidates:
                if self._is_idempotent_skip(policy.id, entity_id, now):
                    skipped_idempotent += 1
                    continue

                message = policy.notification_message_template.format(
                    entity_type=entity_type,
                    entity_id=str(entity_id),
                    condition_type=policy.condition_type,
                )
                sent, queued_at = self._queue_notification(
                    org_id=policy.organization_id,
                    escalated_to=policy.escalate_to_user_id,
                    subject=f"Escalation triggered: {policy.name}",
                    body=message,
                )

                event = EscalationEvent(
                    organization_id=policy.organization_id,
                    policy_id=policy.id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    escalated_at=now,
                    escalated_to=policy.escalate_to_user_id,
                    notification_sent=sent,
                    notification_queued_at=queued_at,
                )
                self.db.add(event)
                self.db.flush()

                AuditService(self.db).write_audit_log(
                    action="escalation.fired",
                    entity_type="escalation_event",
                    entity_id=event.id,
                    organization_id=policy.organization_id,
                    actor_user_id=None,
                    after_json={
                        "policy_id": str(policy.id),
                        "entity_type": entity_type,
                        "entity_id": str(entity_id),
                        "escalated_to": str(policy.escalate_to_user_id),
                    },
                    metadata_json={"source": "scheduler" if org_id is None else "manual"},
                )
                escalations_fired += 1

        return {
            "policies_evaluated": policies_evaluated,
            "escalations_fired": escalations_fired,
            "skipped_idempotent": skipped_idempotent,
        }

    def get_escalation_history(
        self,
        org_id: uuid.UUID,
        *,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
    ) -> list[EscalationEvent]:
        stmt = select(EscalationEvent).where(EscalationEvent.organization_id == org_id)
        if entity_type is not None:
            stmt = stmt.where(EscalationEvent.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(EscalationEvent.entity_id == entity_id)
        return self.db.execute(stmt.order_by(EscalationEvent.escalated_at.desc())).scalars().all()


def run_daily_escalation_policy_evaluation(db: Session) -> dict[str, int]:
    return EscalationService(db).evaluate_policies()
