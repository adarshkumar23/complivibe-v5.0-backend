import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.services.audit_engagement_service import AuditEngagementService
from app.models.audit_engagement import AuditEngagement
from app.models.audit_schedule import AuditSchedule
from app.models.compliance_deadline import ComplianceDeadline
from app.models.email_outbox import EmailOutbox
from app.models.framework import Framework
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from app.schemas.audit_schedule import AuditScheduleCreate, AuditScheduleUpdate
from app.services.audit_service import AuditService


class AuditScheduleService:
    ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
        "active": {"paused", "cancelled"},
        "paused": {"active", "cancelled"},
        "cancelled": set(),
    }

    def __init__(self, db: Session) -> None:
        self.db = db
        self.engagement_service = AuditEngagementService(db)

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def utcdate() -> date:
        return datetime.now(UTC).date()

    @staticmethod
    def compute_next_audit_date(current_date: date, recurrence_pattern: str) -> date:
        offset_days = {
            "annual": 365,
            "semi_annual": 182,
            "quarterly": 91,
            "monthly": 30,
        }
        if recurrence_pattern not in offset_days:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid recurrence_pattern")
        return current_date + timedelta(days=offset_days[recurrence_pattern])

    def require_schedule(self, org_id: uuid.UUID, schedule_id: uuid.UUID) -> AuditSchedule:
        row = self.db.execute(
            select(AuditSchedule).where(
                AuditSchedule.organization_id == org_id,
                AuditSchedule.id == schedule_id,
                AuditSchedule.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit schedule not found")
        return row

    def _require_framework(self, framework_id: uuid.UUID) -> Framework:
        row = self.db.execute(select(Framework).where(Framework.id == framework_id)).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="framework_id not found")
        return row

    def _primary_org_admin_user(self, org_id: uuid.UUID) -> User | None:
        row = self.db.execute(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .join(Role, Role.id == Membership.role_id)
            .where(
                Membership.organization_id == org_id,
                Membership.status == "active",
                Role.name.in_(["owner", "admin"]),
                User.is_active.is_(True),
                User.status == "active",
            )
            .order_by(Role.name.asc(), Membership.created_at.asc())
        ).scalars().first()
        return row

    def _resolve_recipient_users(self, schedule: AuditSchedule) -> list[User]:
        if schedule.last_audit_engagement_id is not None:
            engagement = self.db.execute(
                select(AuditEngagement).where(
                    AuditEngagement.organization_id == schedule.organization_id,
                    AuditEngagement.id == schedule.last_audit_engagement_id,
                    AuditEngagement.deleted_at.is_(None),
                )
            ).scalar_one_or_none()
            if engagement is not None:
                user_ids: list[uuid.UUID] = []
                for item in engagement.assigned_auditor_ids or []:
                    try:
                        user_ids.append(uuid.UUID(item))
                    except ValueError:
                        continue
                if user_ids:
                    users = self.db.execute(
                        select(User).where(
                            User.id.in_(user_ids),
                            User.is_active.is_(True),
                            User.status == "active",
                            User.email.is_not(None),
                        )
                    ).scalars().all()
                    if users:
                        return users

        admin = self._primary_org_admin_user(schedule.organization_id)
        if admin is not None and admin.email:
            return [admin]
        return []

    def create_schedule(self, org_id: uuid.UUID, data: AuditScheduleCreate, created_by: uuid.UUID) -> AuditSchedule:
        self._require_framework(data.framework_id)

        row = AuditSchedule(
            organization_id=org_id,
            title=data.title,
            audit_type=data.audit_type,
            framework_id=data.framework_id,
            recurrence_pattern=data.recurrence_pattern,
            next_audit_date=data.next_audit_date,
            preparation_reminder_days=data.preparation_reminder_days,
            status="active",
            created_by=created_by,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="audit_schedule.created",
            entity_type="audit_schedule",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={
                "title": row.title,
                "audit_type": row.audit_type,
                "framework_id": str(row.framework_id),
                "recurrence_pattern": row.recurrence_pattern,
                "next_audit_date": str(row.next_audit_date),
                "status": row.status,
            },
            metadata_json={"source": "api"},
        )
        return row

    def get_schedule(self, org_id: uuid.UUID, schedule_id: uuid.UUID) -> AuditSchedule:
        return self.require_schedule(org_id, schedule_id)

    def list_schedules(
        self,
        org_id: uuid.UUID,
        *,
        status_value: str | None = None,
        framework_id: uuid.UUID | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[AuditSchedule]:
        stmt = select(AuditSchedule).where(
            AuditSchedule.organization_id == org_id,
            AuditSchedule.deleted_at.is_(None),
        )
        if status_value is not None:
            stmt = stmt.where(AuditSchedule.status == status_value)
        if framework_id is not None:
            stmt = stmt.where(AuditSchedule.framework_id == framework_id)

        rows = self.db.execute(stmt.order_by(AuditSchedule.next_audit_date.asc(), AuditSchedule.created_at.desc())).scalars().all()
        return rows[skip : skip + limit]

    def update_schedule(self, org_id: uuid.UUID, schedule_id: uuid.UUID, data: AuditScheduleUpdate) -> AuditSchedule:
        row = self.require_schedule(org_id, schedule_id)
        updates = data.model_dump(exclude_unset=True)

        before = {
            "title": row.title,
            "next_audit_date": str(row.next_audit_date),
            "preparation_reminder_days": row.preparation_reminder_days,
            "recurrence_pattern": row.recurrence_pattern,
        }
        for key, value in updates.items():
            setattr(row, key, value)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="audit_schedule.updated",
            entity_type="audit_schedule",
            entity_id=row.id,
            organization_id=org_id,
            before_json=before,
            after_json={
                "title": row.title,
                "next_audit_date": str(row.next_audit_date),
                "preparation_reminder_days": row.preparation_reminder_days,
                "recurrence_pattern": row.recurrence_pattern,
            },
            metadata_json={"source": "api"},
        )
        return row

    def set_schedule_status(
        self,
        org_id: uuid.UUID,
        schedule_id: uuid.UUID,
        new_status: str,
        user_id: uuid.UUID,
    ) -> AuditSchedule:
        row = self.require_schedule(org_id, schedule_id)
        allowed = self.ALLOWED_STATUS_TRANSITIONS.get(row.status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status transition from {row.status} to {new_status}",
            )

        before = row.status
        row.status = new_status
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="audit_schedule.status_changed",
            entity_type="audit_schedule",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            before_json={"status": before},
            after_json={"status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def link_engagement(
        self,
        org_id: uuid.UUID,
        schedule_id: uuid.UUID,
        engagement_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> AuditSchedule:
        row = self.require_schedule(org_id, schedule_id)
        self.engagement_service.require_engagement(org_id, engagement_id)

        before = {
            "last_audit_engagement_id": str(row.last_audit_engagement_id) if row.last_audit_engagement_id else None,
            "next_audit_date": str(row.next_audit_date),
        }

        row.last_audit_engagement_id = engagement_id
        row.next_audit_date = self.compute_next_audit_date(row.next_audit_date, row.recurrence_pattern)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="audit_schedule.engagement_linked",
            entity_type="audit_schedule",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            before_json=before,
            after_json={
                "last_audit_engagement_id": str(row.last_audit_engagement_id),
                "next_audit_date": str(row.next_audit_date),
            },
            metadata_json={"source": "api"},
        )
        return row

    def _queue_reminder(self, schedule: AuditSchedule, recipient: User, days_until: int, framework_name: str | None) -> None:
        subject = f"Audit preparation reminder: {schedule.title}"
        body = (
            f"Audit schedule: {schedule.title}\n"
            f"Next audit date: {schedule.next_audit_date.isoformat()}\n"
            f"Framework: {framework_name or 'N/A'}\n"
            f"Days until audit: {days_until}\n"
        )

        self.db.add(
            EmailOutbox(
                organization_id=schedule.organization_id,
                template_id=None,
                event_type="audit.schedule.reminder",
                recipient_email=recipient.email,
                recipient_user_id=recipient.id,
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
                    "source": "audit_schedule_reminder",
                    "schedule_id": str(schedule.id),
                    "next_audit_date": schedule.next_audit_date.isoformat(),
                },
                created_by_user_id=schedule.created_by,
            )
        )

    def _create_calendar_deadline_if_missing(self, schedule: AuditSchedule, owner_user_id: uuid.UUID, framework_name: str | None) -> bool:
        existing = self.db.execute(
            select(ComplianceDeadline.id).where(
                ComplianceDeadline.organization_id == schedule.organization_id,
                ComplianceDeadline.linked_entity_type == "audit_schedule",
                ComplianceDeadline.linked_entity_id == schedule.id,
                ComplianceDeadline.due_date == schedule.next_audit_date,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return False

        self.db.add(
            ComplianceDeadline(
                organization_id=schedule.organization_id,
                title=f"Prepare for audit: {schedule.title}",
                description=f"Upcoming scheduled audit for framework {framework_name or 'N/A'}.",
                deadline_type="audit_preparation",
                due_date=schedule.next_audit_date,
                status="upcoming",
                priority="high",
                owner_user_id=owner_user_id,
                linked_entity_type="audit_schedule",
                linked_entity_id=schedule.id,
                reminder_days_before=schedule.preparation_reminder_days,
                created_by_user_id=schedule.created_by,
            )
        )
        return True

    def process_schedule_reminders(self) -> dict[str, int]:
        today = self.utcdate()
        processed = 0
        reminders_sent = 0
        calendars_created = 0

        schedules = self.db.execute(
            select(AuditSchedule).where(
                AuditSchedule.deleted_at.is_(None),
                AuditSchedule.status == "active",
            )
        ).scalars().all()

        for schedule in schedules:
            days_until = (schedule.next_audit_date - today).days
            if days_until > int(schedule.preparation_reminder_days):
                continue

            if schedule.last_reminder_sent_at is not None:
                last_reminder_date = schedule.last_reminder_sent_at.date()
                if last_reminder_date >= (today - timedelta(days=7)):
                    continue

            framework = self.db.execute(select(Framework).where(Framework.id == schedule.framework_id)).scalar_one_or_none()
            framework_name = framework.name if framework is not None else None

            recipients = self._resolve_recipient_users(schedule)
            if not recipients:
                continue

            for recipient in recipients:
                self._queue_reminder(schedule, recipient, days_until, framework_name)
            reminders_sent += 1

            created = self._create_calendar_deadline_if_missing(schedule, recipients[0].id, framework_name)
            if created:
                calendars_created += 1

            schedule.last_reminder_sent_at = self.utcnow()
            processed += 1

            AuditService(self.db).write_audit_log(
                action="audit_schedule.reminder_processed",
                entity_type="audit_schedule",
                entity_id=schedule.id,
                organization_id=schedule.organization_id,
                actor_user_id=None,
                after_json={
                    "next_audit_date": str(schedule.next_audit_date),
                    "days_until": days_until,
                    "recipient_count": len(recipients),
                },
                metadata_json={"source": "scheduler"},
            )

        self.db.flush()
        return {
            "processed": processed,
            "reminders_sent": reminders_sent,
            "calendars_created": calendars_created,
        }

    def get_schedule_history(self, org_id: uuid.UUID, schedule_id: uuid.UUID) -> list[AuditEngagement]:
        _ = self.require_schedule(org_id, schedule_id)
        return self.db.execute(
            select(AuditEngagement)
            .where(
                AuditEngagement.organization_id == org_id,
                AuditEngagement.deleted_at.is_(None),
            )
            .order_by(AuditEngagement.start_date.desc(), AuditEngagement.created_at.desc())
        ).scalars().all()

    def soft_delete_schedule(self, org_id: uuid.UUID, schedule_id: uuid.UUID, user_id: uuid.UUID) -> AuditSchedule:
        row = self.require_schedule(org_id, schedule_id)
        if row.status == "active":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Active schedules cannot be deleted")

        before = {
            "status": row.status,
            "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
        }
        if row.status != "cancelled":
            row.status = "cancelled"
        row.deleted_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="audit_schedule.updated",
            entity_type="audit_schedule",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            before_json=before,
            after_json={
                "status": row.status,
                "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
            },
            metadata_json={"source": "api"},
        )
        return row


def run_daily_audit_schedule_reminder_sweep(db: Session) -> dict[str, int]:
    return AuditScheduleService(db).process_schedule_reminders()
