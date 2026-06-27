import uuid
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.commitment_notification_log import CommitmentNotificationLog
from app.models.customer_commitment import CustomerCommitment
from app.models.email_outbox import EmailOutbox
from app.models.membership import Membership
from app.models.user import User
from app.services.audit_service import AuditService


class CustomerCommitmentService:
    STATUS_TRANSITIONS: dict[str, set[str]] = {
        "active": {"triggered"},
        "triggered": {"fulfilled", "overdue", "waived"},
        "overdue": {"fulfilled", "waived"},
        "fulfilled": set(),
        "waived": set(),
        "expired": set(),
    }

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def utcdate() -> date:
        return datetime.now(UTC).date()

    def _require_active_member(self, org_id: uuid.UUID, user_id: uuid.UUID) -> User:
        membership = self.db.execute(
            select(Membership).where(
                Membership.organization_id == org_id,
                Membership.user_id == user_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="assigned_owner_id must be an active member")

        user = self.db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if user is None or not user.is_active or user.status != "active":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="assigned_owner_id must be an active member")
        return user

    def require_commitment(self, org_id: uuid.UUID, commitment_id: uuid.UUID) -> CustomerCommitment:
        row = self.db.execute(
            select(CustomerCommitment).where(
                CustomerCommitment.id == commitment_id,
                CustomerCommitment.organization_id == org_id,
                CustomerCommitment.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer commitment not found")
        return row

    def _queue_notification(
        self,
        commitment: CustomerCommitment,
        *,
        notification_type: str,
        triggered_by: str,
        subject: str,
        body: str,
    ) -> int:
        owner = self.db.execute(select(User).where(User.id == commitment.assigned_owner_id)).scalar_one_or_none()
        recipient_ids: list[str] = []
        queued_count = 0

        if owner is not None and owner.email:
            self.db.add(
                EmailOutbox(
                    organization_id=commitment.organization_id,
                    template_id=None,
                    event_type=f"customer_commitment.{notification_type}",
                    recipient_email=owner.email,
                    recipient_user_id=owner.id,
                    subject=subject,
                    body_text=body,
                    body_html=None,
                    status="pending",
                    priority="normal",
                    scheduled_at=None,
                    queued_at=self.utcnow(),
                    attempt_count=0,
                    max_attempts=3,
                    metadata_json={
                        "source": "customer_commitment_workflow",
                        "commitment_id": str(commitment.id),
                        "notification_type": notification_type,
                    },
                    created_by_user_id=commitment.created_by,
                )
            )
            recipient_ids.append(str(owner.id))
            queued_count += 1

        self.db.add(
            CommitmentNotificationLog(
                organization_id=commitment.organization_id,
                commitment_id=commitment.id,
                notification_type=notification_type,
                queued_at=self.utcnow(),
                recipient_user_ids=recipient_ids,
                message_preview=body[:255],
                triggered_by=triggered_by,
            )
        )
        return queued_count

    def _check_transition(self, current_status: str, new_status: str) -> None:
        allowed = self.STATUS_TRANSITIONS.get(current_status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status transition from {current_status} to {new_status}",
            )

    def create_commitment(self, org_id: uuid.UUID, data, created_by: uuid.UUID) -> CustomerCommitment:
        self._require_active_member(org_id, data.assigned_owner_id)

        row = CustomerCommitment(
            organization_id=org_id,
            customer_name=data.customer_name,
            customer_email=data.customer_email,
            commitment_type=data.commitment_type,
            title=data.title,
            description=data.description,
            trigger_condition=data.trigger_condition,
            trigger_date=data.trigger_date,
            notification_days_before=data.notification_days_before,
            sla_hours=data.sla_hours,
            status="active",
            linked_contract_ref=data.linked_contract_ref,
            assigned_owner_id=data.assigned_owner_id,
            created_by=created_by,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="customer_commitment.created",
            entity_type="customer_commitment",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={"title": row.title, "status": row.status, "commitment_type": row.commitment_type},
            metadata_json={"source": "api"},
        )
        return row

    def get_commitment(self, org_id: uuid.UUID, commitment_id: uuid.UUID) -> CustomerCommitment:
        return self.require_commitment(org_id, commitment_id)

    def list_commitments(
        self,
        org_id: uuid.UUID,
        *,
        commitment_type: str | None = None,
        status_value: str | None = None,
        customer_name: str | None = None,
        assigned_owner_id: uuid.UUID | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[CustomerCommitment]:
        stmt = select(CustomerCommitment).where(
            CustomerCommitment.organization_id == org_id,
            CustomerCommitment.deleted_at.is_(None),
        )
        if commitment_type is not None:
            stmt = stmt.where(CustomerCommitment.commitment_type == commitment_type)
        if status_value is not None:
            stmt = stmt.where(CustomerCommitment.status == status_value)
        if customer_name is not None:
            stmt = stmt.where(CustomerCommitment.customer_name.ilike(f"%{customer_name}%"))
        if assigned_owner_id is not None:
            stmt = stmt.where(CustomerCommitment.assigned_owner_id == assigned_owner_id)

        return self.db.execute(stmt.order_by(CustomerCommitment.created_at.desc()).offset(skip).limit(limit)).scalars().all()

    def update_commitment(self, org_id: uuid.UUID, commitment_id: uuid.UUID, data, *, actor_user_id: uuid.UUID | None = None) -> CustomerCommitment:
        row = self.require_commitment(org_id, commitment_id)
        changes = data.model_dump(exclude_unset=True)
        if "assigned_owner_id" in changes and changes["assigned_owner_id"] is not None:
            self._require_active_member(org_id, changes["assigned_owner_id"])

        before = {
            "title": row.title,
            "customer_name": row.customer_name,
            "trigger_date": row.trigger_date.isoformat() if row.trigger_date else None,
            "assigned_owner_id": str(row.assigned_owner_id),
        }
        for field, value in changes.items():
            setattr(row, field, value)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="customer_commitment.updated",
            entity_type="customer_commitment",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json={
                "title": row.title,
                "customer_name": row.customer_name,
                "trigger_date": row.trigger_date.isoformat() if row.trigger_date else None,
                "assigned_owner_id": str(row.assigned_owner_id),
            },
            metadata_json={"source": "api"},
        )
        return row

    def trigger_commitment(
        self,
        org_id: uuid.UUID,
        commitment_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        triggered_by: str = "manual",
    ) -> CustomerCommitment:
        row = self.require_commitment(org_id, commitment_id)
        self._check_transition(row.status, "triggered")

        row.status = "triggered"
        row.triggered_at = self.utcnow()

        subject = f"Commitment triggered: {row.title}"
        body = (
            f"Customer commitment triggered.\n"
            f"Title: {row.title}\n"
            f"Customer: {row.customer_name}\n"
            f"Condition: {row.trigger_condition}\n"
        )
        self._queue_notification(
            row,
            notification_type="triggered",
            triggered_by=triggered_by,
            subject=subject,
            body=body,
        )

        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="customer_commitment.triggered",
            entity_type="customer_commitment",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status, "triggered_at": row.triggered_at.isoformat() if row.triggered_at else None},
            metadata_json={"source": "api", "triggered_by": triggered_by},
        )
        return row

    def fulfill_commitment(
        self,
        org_id: uuid.UUID,
        commitment_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        notes: str | None = None,
    ) -> CustomerCommitment:
        row = self.require_commitment(org_id, commitment_id)
        self._check_transition(row.status, "fulfilled")

        row.status = "fulfilled"
        row.fulfilled_at = self.utcnow()
        row.fulfilled_by = user_id
        row.fulfillment_notes = notes

        self._queue_notification(
            row,
            notification_type="fulfilled",
            triggered_by="api",
            subject=f"Commitment fulfilled: {row.title}",
            body=(
                f"Customer commitment fulfilled.\n"
                f"Title: {row.title}\n"
                f"Customer: {row.customer_name}\n"
            ),
        )

        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="customer_commitment.fulfilled",
            entity_type="customer_commitment",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status, "fulfilled_at": row.fulfilled_at.isoformat() if row.fulfilled_at else None},
            metadata_json={"source": "api"},
        )
        return row

    def waive_commitment(self, org_id: uuid.UUID, commitment_id: uuid.UUID, user_id: uuid.UUID, *, reason: str) -> CustomerCommitment:
        row = self.require_commitment(org_id, commitment_id)
        self._check_transition(row.status, "waived")

        row.status = "waived"
        row.waived_at = self.utcnow()
        row.waived_by = user_id
        row.waiver_reason = reason
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="customer_commitment.waived",
            entity_type="customer_commitment",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status, "waived_at": row.waived_at.isoformat() if row.waived_at else None},
            metadata_json={"source": "api"},
        )
        return row

    def _has_reminder_today(self, commitment_id: uuid.UUID, now: datetime) -> bool:
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        existing = self.db.execute(
            select(CommitmentNotificationLog.id).where(
                CommitmentNotificationLog.commitment_id == commitment_id,
                CommitmentNotificationLog.notification_type == "reminder",
                CommitmentNotificationLog.queued_at >= day_start,
                CommitmentNotificationLog.queued_at < day_end,
            )
        ).scalar_one_or_none()
        return existing is not None

    def process_commitment_triggers(self) -> dict[str, int]:
        today = self.utcdate()
        now = self.utcnow()

        reminders = 0
        triggered = 0
        overdue = 0
        notifications_queued = 0

        per_org = defaultdict(lambda: {"reminders": 0, "triggered": 0, "overdue": 0, "notifications_queued": 0})

        active_rows = self.db.execute(
            select(CustomerCommitment).where(
                CustomerCommitment.deleted_at.is_(None),
                CustomerCommitment.status == "active",
                CustomerCommitment.trigger_date.is_not(None),
            )
        ).scalars().all()

        # Step 1 reminder sweep
        for row in active_rows:
            if row.trigger_date is None:
                continue
            if row.trigger_date > (today + timedelta(days=int(row.notification_days_before))):
                continue
            if self._has_reminder_today(row.id, now):
                continue

            queued = self._queue_notification(
                row,
                notification_type="reminder",
                triggered_by="scheduler",
                subject=f"Commitment reminder: {row.title}",
                body=(
                    f"Customer commitment reminder.\n"
                    f"Title: {row.title}\n"
                    f"Customer: {row.customer_name}\n"
                    f"Trigger date: {row.trigger_date.isoformat()}\n"
                ),
            )
            reminders += 1
            notifications_queued += queued
            per_org[row.organization_id]["reminders"] += 1
            per_org[row.organization_id]["notifications_queued"] += queued

        self.db.flush()

        # Step 2 trigger sweep
        for row in active_rows:
            if row.trigger_date is None:
                continue
            if row.status != "active":
                continue
            if row.trigger_date <= today:
                self.trigger_commitment(
                    row.organization_id,
                    row.id,
                    user_id=row.created_by,
                    triggered_by="scheduler",
                )
                triggered += 1
                notifications_queued += 1
                per_org[row.organization_id]["triggered"] += 1
                per_org[row.organization_id]["notifications_queued"] += 1

        # Step 3 overdue sweep
        overdue_rows = self.db.execute(
            select(CustomerCommitment).where(
                CustomerCommitment.deleted_at.is_(None),
                CustomerCommitment.status == "triggered",
                CustomerCommitment.trigger_date.is_not(None),
                CustomerCommitment.trigger_date < (today - timedelta(days=3)),
            )
        ).scalars().all()

        for row in overdue_rows:
            self._check_transition(row.status, "overdue")
            row.status = "overdue"
            queued = self._queue_notification(
                row,
                notification_type="escalation",
                triggered_by="scheduler",
                subject=f"Commitment overdue: {row.title}",
                body=(
                    f"Customer commitment overdue.\n"
                    f"Title: {row.title}\n"
                    f"Customer: {row.customer_name}\n"
                    f"Trigger date: {row.trigger_date.isoformat() if row.trigger_date else 'N/A'}\n"
                ),
            )
            overdue += 1
            notifications_queued += queued
            per_org[row.organization_id]["overdue"] += 1
            per_org[row.organization_id]["notifications_queued"] += queued

        self.db.flush()

        for audit_org_id, counts in per_org.items():
            AuditService(self.db).write_audit_log(
                action="customer_commitment.sweep_processed",
                entity_type="customer_commitment",
                organization_id=audit_org_id,
                actor_user_id=None,
                after_json=counts,
                metadata_json={"source": "scheduler"},
            )

        return {
            "reminders": reminders,
            "triggered": triggered,
            "overdue": overdue,
            "notifications_queued": notifications_queued,
        }

    def get_commitment_dashboard(self, org_id: uuid.UUID) -> dict:
        today = self.utcdate()
        window_30 = today + timedelta(days=30)

        rows = self.db.execute(
            select(CustomerCommitment).where(
                CustomerCommitment.organization_id == org_id,
                CustomerCommitment.deleted_at.is_(None),
            )
        ).scalars().all()

        by_type = Counter(row.commitment_type for row in rows)
        by_status = Counter(row.status for row in rows)

        month_start = date(today.year, today.month, 1)
        if today.month == 12:
            next_month_start = date(today.year + 1, 1, 1)
        else:
            next_month_start = date(today.year, today.month + 1, 1)

        fulfilled_this_month = int(
            self.db.execute(
                select(func.count(CustomerCommitment.id)).where(
                    CustomerCommitment.organization_id == org_id,
                    CustomerCommitment.deleted_at.is_(None),
                    CustomerCommitment.status == "fulfilled",
                    CustomerCommitment.fulfilled_at.is_not(None),
                    CustomerCommitment.fulfilled_at >= datetime(month_start.year, month_start.month, month_start.day, tzinfo=UTC),
                    CustomerCommitment.fulfilled_at < datetime(next_month_start.year, next_month_start.month, next_month_start.day, tzinfo=UTC),
                )
            ).scalar_one()
        )

        due_within_30_days = int(
            self.db.execute(
                select(func.count(CustomerCommitment.id)).where(
                    CustomerCommitment.organization_id == org_id,
                    CustomerCommitment.deleted_at.is_(None),
                    CustomerCommitment.status == "active",
                    CustomerCommitment.trigger_date.is_not(None),
                    CustomerCommitment.trigger_date <= window_30,
                )
            ).scalar_one()
        )

        breach_rows = [
            row
            for row in rows
            if row.commitment_type == "breach_notification"
            and row.triggered_at is not None
            and row.fulfilled_at is not None
            and row.sla_hours is not None
            and row.sla_hours > 0
        ]
        fulfilled_within_sla = 0
        breached_sla = 0
        for row in breach_rows:
            elapsed_hours = int((row.fulfilled_at - row.triggered_at).total_seconds() // 3600)
            if elapsed_hours <= int(row.sla_hours):
                fulfilled_within_sla += 1
            else:
                breached_sla += 1
        compliance_rate = float((fulfilled_within_sla / len(breach_rows)) * 100) if breach_rows else 0.0

        return {
            "total": len(rows),
            "by_type": {k: int(v) for k, v in by_type.items()},
            "by_status": {k: int(v) for k, v in by_status.items()},
            "overdue_count": int(by_status.get("overdue", 0)),
            "triggered_count": int(by_status.get("triggered", 0)),
            "due_within_30_days": due_within_30_days,
            "fulfilled_this_month": fulfilled_this_month,
            "breach_notification_sla_compliance": {
                "total_breach_commitments": len(breach_rows),
                "fulfilled_within_sla": fulfilled_within_sla,
                "breached_sla": breached_sla,
                "compliance_rate": compliance_rate,
            },
        }

    def list_notification_logs(self, org_id: uuid.UUID, commitment_id: uuid.UUID) -> list[CommitmentNotificationLog]:
        _ = self.require_commitment(org_id, commitment_id)
        return self.db.execute(
            select(CommitmentNotificationLog)
            .where(
                CommitmentNotificationLog.organization_id == org_id,
                CommitmentNotificationLog.commitment_id == commitment_id,
            )
            .order_by(CommitmentNotificationLog.queued_at.desc())
        ).scalars().all()

    def soft_delete_commitment(self, org_id: uuid.UUID, commitment_id: uuid.UUID, user_id: uuid.UUID) -> CustomerCommitment:
        row = self.require_commitment(org_id, commitment_id)
        if row.status != "active":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only active commitments can be deleted")

        row.deleted_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="customer_commitment.deleted",
            entity_type="customer_commitment",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"deleted_at": row.deleted_at.isoformat() if row.deleted_at else None},
            metadata_json={"source": "api"},
        )
        return row


def run_daily_customer_commitment_trigger_sweep(db: Session) -> dict[str, int]:
    return CustomerCommitmentService(db).process_commitment_triggers()
