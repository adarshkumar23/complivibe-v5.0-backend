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
from app.schemas.audit_engagement import AuditEngagementCreate
from app.schemas.audit_schedule import AuditScheduleCreate, AuditScheduleUpdate
from app.services.audit_service import AuditService
from app.core.validation import validate_choice


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
    def _normalize_recurrence(recurrence: str) -> str:
        value = recurrence.strip().lower()
        allowed = {"monthly", "quarterly", "semi_annual", "annual"}
        value = validate_choice(value, allowed, "recurrence")
        return value

    @staticmethod
    def compute_next_audit_date(current_date: date, recurrence_pattern: str) -> date:
        offset_days = {
            "annual": 365,
            "semi_annual": 182,
            "quarterly": 91,
            "monthly": 30,
        }
        recurrence_pattern = validate_choice(recurrence_pattern, offset_days, "recurrence_pattern")
        return current_date + timedelta(days=offset_days[recurrence_pattern])

    def _compute_initial_due_date(self, recurrence: str, anchor: date | None = None) -> date:
        today = anchor or self.utcdate()
        recurrence = self._normalize_recurrence(recurrence)
        if recurrence == "monthly":
            year = today.year + (1 if today.month == 12 else 0)
            month = 1 if today.month == 12 else today.month + 1
            return date(year, month, 1)
        if recurrence == "quarterly":
            quarter = (today.month - 1) // 3
            next_quarter = quarter + 1
            year = today.year + (1 if next_quarter == 4 else 0)
            month = ((next_quarter % 4) * 3) + 1
            return date(year, month, 1)
        if recurrence == "semi_annual":
            return today + timedelta(days=182)
        return today + timedelta(days=365)

    def _advance_due_date(self, current_due: date, recurrence: str) -> date:
        recurrence = self._normalize_recurrence(recurrence)
        if recurrence == "monthly":
            year = current_due.year + (1 if current_due.month == 12 else 0)
            month = 1 if current_due.month == 12 else current_due.month + 1
            return date(year, month, 1)
        if recurrence == "quarterly":
            month = current_due.month + 3
            year = current_due.year
            while month > 12:
                month -= 12
                year += 1
            return date(year, month, 1)
        if recurrence == "semi_annual":
            return current_due + timedelta(days=182)
        return current_due + timedelta(days=365)

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

    def create_schedule(
        self,
        org_id: uuid.UUID,
        data: AuditScheduleCreate | None = None,
        created_by: uuid.UUID | None = None,
        *,
        title: str | None = None,
        recurrence: str | None = None,
        lead_time_days: int = 30,
        audit_type: str | None = None,
        framework_id: uuid.UUID | None = None,
        assigned_lead_auditor_id: uuid.UUID | None = None,
    ) -> AuditSchedule:
        # Backward-compatible path used by existing v1 API.
        if data is not None:
            if created_by is None:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="created_by is required")
            self._require_framework(data.framework_id)
            row = AuditSchedule(
                organization_id=org_id,
                title=data.title,
                audit_type=data.audit_type,
                framework_id=data.framework_id,
                recurrence_pattern=data.recurrence_pattern,
                recurrence=data.recurrence_pattern,
                next_audit_date=data.next_audit_date,
                next_due_date=data.next_audit_date,
                preparation_reminder_days=data.preparation_reminder_days,
                lead_time_days=data.preparation_reminder_days,
                status="active",
                is_active=True,
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
                    "framework_id": str(row.framework_id) if row.framework_id else None,
                    "recurrence": row.recurrence,
                    "next_due_date": str(row.next_due_date),
                    "lead_time_days": row.lead_time_days,
                    "is_active": row.is_active,
                },
                metadata_json={"source": "api"},
            )
            return row

        # New scheduling contract used by Sprint 3 prompt.
        if created_by is None or title is None or recurrence is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="title, recurrence, and created_by are required",
            )

        if framework_id is not None:
            self._require_framework(framework_id)

        recurrence_value = self._normalize_recurrence(recurrence)
        next_due = self._compute_initial_due_date(recurrence_value)
        row = AuditSchedule(
            organization_id=org_id,
            title=title,
            audit_type=audit_type,
            framework_id=framework_id,
            recurrence_pattern=recurrence_value,
            recurrence=recurrence_value,
            next_audit_date=next_due,
            next_due_date=next_due,
            preparation_reminder_days=lead_time_days,
            lead_time_days=lead_time_days,
            assigned_lead_auditor_id=assigned_lead_auditor_id,
            status="active",
            is_active=True,
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
                "framework_id": str(row.framework_id) if row.framework_id else None,
                "recurrence": row.recurrence,
                "next_due_date": str(row.next_due_date),
                "lead_time_days": row.lead_time_days,
                "is_active": row.is_active,
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
        is_active: bool | None = None,
        skip: int = 0,
        limit: int = 50,
        page: int | None = None,
        page_size: int | None = None,
    ) -> list[AuditSchedule]:
        stmt = select(AuditSchedule).where(
            AuditSchedule.organization_id == org_id,
            AuditSchedule.deleted_at.is_(None),
        )
        if status_value is not None:
            stmt = stmt.where(AuditSchedule.status == status_value)
        if framework_id is not None:
            stmt = stmt.where(AuditSchedule.framework_id == framework_id)
        if is_active is not None:
            stmt = stmt.where(AuditSchedule.is_active.is_(is_active))

        rows = self.db.execute(stmt.order_by(AuditSchedule.next_due_date.asc(), AuditSchedule.created_at.desc())).scalars().all()

        if page is not None and page_size is not None:
            start = (page - 1) * page_size
            return rows[start : start + page_size]
        return rows[skip : skip + limit]

    def update_schedule(
        self,
        org_id: uuid.UUID,
        schedule_id: uuid.UUID,
        data: AuditScheduleUpdate | None = None,
        **fields,
    ) -> AuditSchedule:
        row = self.require_schedule(org_id, schedule_id)
        updates: dict = {}
        if data is not None:
            updates.update(data.model_dump(exclude_unset=True))
        updates.update({k: v for k, v in fields.items() if v is not None})

        before = {
            "title": row.title,
            "next_due_date": str(row.next_due_date) if row.next_due_date else None,
            "lead_time_days": row.lead_time_days,
            "recurrence": row.recurrence,
            "is_active": row.is_active,
        }

        if "recurrence" in updates:
            recurrence_value = self._normalize_recurrence(updates["recurrence"])
            updates["recurrence"] = recurrence_value
            updates["recurrence_pattern"] = recurrence_value
            updates["next_due_date"] = self._compute_initial_due_date(recurrence_value)
            updates["next_audit_date"] = updates["next_due_date"]

        if "recurrence_pattern" in updates:
            recurrence_value = self._normalize_recurrence(updates["recurrence_pattern"])
            updates["recurrence_pattern"] = recurrence_value
            updates["recurrence"] = recurrence_value

        if "lead_time_days" in updates:
            updates["preparation_reminder_days"] = updates["lead_time_days"]
        if "preparation_reminder_days" in updates and "lead_time_days" not in updates:
            updates["lead_time_days"] = updates["preparation_reminder_days"]

        if "next_due_date" in updates and "next_audit_date" not in updates:
            updates["next_audit_date"] = updates["next_due_date"]
        if "next_audit_date" in updates and "next_due_date" not in updates:
            updates["next_due_date"] = updates["next_audit_date"]

        if "is_active" in updates:
            updates["status"] = "active" if updates["is_active"] else "paused"

        allowed = {
            "title",
            "recurrence",
            "lead_time_days",
            "audit_type",
            "framework_id",
            "assigned_lead_auditor_id",
            "is_active",
            "next_due_date",
            "recurrence_pattern",
            "next_audit_date",
            "preparation_reminder_days",
            "status",
        }
        for key, value in updates.items():
            if key in allowed:
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
                "next_due_date": str(row.next_due_date) if row.next_due_date else None,
                "lead_time_days": row.lead_time_days,
                "recurrence": row.recurrence,
                "is_active": row.is_active,
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
        row.is_active = new_status == "active"
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="audit_schedule.status_changed",
            entity_type="audit_schedule",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            before_json={"status": before},
            after_json={"status": row.status, "is_active": row.is_active},
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
        engagement = self.engagement_service.require_engagement(org_id, engagement_id)

        before = {
            "last_audit_engagement_id": str(row.last_audit_engagement_id) if row.last_audit_engagement_id else None,
            "next_due_date": str(row.next_due_date) if row.next_due_date else None,
        }

        row.last_audit_engagement_id = engagement_id
        current_due = row.next_due_date or row.next_audit_date
        row.next_due_date = self._advance_due_date(current_due, row.recurrence)
        row.next_audit_date = row.next_due_date

        # Manually-linked engagements must be attributed back to the schedule the
        # same way auto-created ones are (source_schedule_id), otherwise
        # get_schedule_history()'s source_schedule_id filter silently drops them.
        if engagement.source_schedule_id is None:
            engagement.source_schedule_id = row.id
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
                "next_due_date": str(row.next_due_date) if row.next_due_date else None,
                "engagement_source_schedule_id": str(engagement.source_schedule_id),
            },
            metadata_json={"source": "api", "link_type": "manual"},
        )
        return row

    def _queue_reminder(self, schedule: AuditSchedule, recipient: User, days_until: int, framework_name: str | None) -> None:
        subject = f"Audit preparation reminder: {schedule.title}"
        due = schedule.next_due_date or schedule.next_audit_date
        body = (
            f"Audit schedule: {schedule.title}\n"
            f"Next audit date: {due.isoformat()}\n"
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
                    "next_due_date": due.isoformat(),
                },
                created_by_user_id=schedule.created_by,
            )
        )

    def _create_calendar_deadline_if_missing(self, schedule: AuditSchedule, owner_user_id: uuid.UUID, framework_name: str | None) -> bool:
        due = schedule.next_due_date or schedule.next_audit_date
        existing = self.db.execute(
            select(ComplianceDeadline.id).where(
                ComplianceDeadline.organization_id == schedule.organization_id,
                ComplianceDeadline.linked_entity_type == "audit_schedule",
                ComplianceDeadline.linked_entity_id == schedule.id,
                ComplianceDeadline.due_date == due,
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
                due_date=due,
                status="upcoming",
                priority="high",
                owner_user_id=owner_user_id,
                linked_entity_type="audit_schedule",
                linked_entity_id=schedule.id,
                reminder_days_before=schedule.lead_time_days,
                created_by_user_id=schedule.created_by,
            )
        )
        return True

    def process_schedule_reminders(self, *, organization_id: uuid.UUID | None = None) -> dict[str, int]:
        """Send due audit-prep reminders.

        organization_id=None sweeps every tenant and is correct ONLY for the scheduled
        fleet-wide job. Any caller reached from an HTTP request must pass its own org:
        this previously took no org argument at all, so the /trigger-reminder-sweep
        endpoint discarded its authenticated organization and swept the whole fleet --
        one tenant's admin could fire audit-prep emails into every other tenant, stamp
        their last_reminder_sent_at, and (via the 7-day debounce below) suppress those
        tenants' own legitimate reminders for a week.
        """
        today = self.utcdate()
        processed = 0
        reminders_sent = 0
        calendars_created = 0

        conditions = [
            AuditSchedule.deleted_at.is_(None),
            AuditSchedule.status == "active",
            AuditSchedule.is_active.is_(True),
        ]
        if organization_id is not None:
            conditions.append(AuditSchedule.organization_id == organization_id)

        schedules = self.db.execute(select(AuditSchedule).where(*conditions)).scalars().all()

        for schedule in schedules:
            due = schedule.next_due_date or schedule.next_audit_date
            days_until = (due - today).days
            if days_until > int(schedule.lead_time_days):
                continue

            if schedule.last_reminder_sent_at is not None:
                last_reminder_date = schedule.last_reminder_sent_at.date()
                if last_reminder_date >= (today - timedelta(days=7)):
                    continue

            framework_name: str | None = None
            if schedule.framework_id is not None:
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
                    "next_due_date": due.isoformat(),
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

    def run_scheduled_audit_creation(self, org_id: uuid.UUID | None = None) -> int:
        today = self.utcdate()
        stmt = select(AuditSchedule).where(
            AuditSchedule.deleted_at.is_(None),
            AuditSchedule.is_active.is_(True),
            AuditSchedule.status == "active",
            AuditSchedule.next_due_date.is_not(None),
        )
        if org_id is not None:
            stmt = stmt.where(AuditSchedule.organization_id == org_id)

        schedules = self.db.execute(stmt).scalars().all()
        created_count = 0

        for schedule in schedules:
            due = schedule.next_due_date
            if due is None:
                continue
            trigger_date = today + timedelta(days=int(schedule.lead_time_days))
            if due > trigger_date:
                continue

            if schedule.last_triggered_at is not None and schedule.last_triggered_at.date() >= due:
                continue

            start_date = today
            end_date = due if due >= start_date else start_date
            engagement_payload = AuditEngagementCreate(
                title=f"{schedule.title} - {due.strftime('%B %Y')}",
                audit_type=schedule.audit_type or "internal_readiness",
                scope_framework_ids=[schedule.framework_id] if schedule.framework_id else [],
                assigned_auditor_ids=[schedule.assigned_lead_auditor_id] if schedule.assigned_lead_auditor_id else [],
                start_date=start_date,
                end_date=end_date,
                lead_auditor_name=None,
                audit_firm=None,
                notes="Auto-created from audit schedule",
            )
            engagement = self.engagement_service.create_engagement(
                schedule.organization_id,
                engagement_payload,
                created_by=schedule.created_by,
                source_schedule_id=schedule.id,
            )

            self.db.add(
                ComplianceDeadline(
                    organization_id=schedule.organization_id,
                    title=f"Audit Due: {schedule.title}",
                    description=f"Auto-created deadline for engagement {engagement.title}",
                    deadline_type="audit_due",
                    due_date=due,
                    status="upcoming",
                    priority="high",
                    owner_user_id=schedule.assigned_lead_auditor_id or schedule.created_by,
                    linked_entity_type="audit_engagement",
                    linked_entity_id=engagement.id,
                    reminder_days_before=schedule.lead_time_days,
                    created_by_user_id=schedule.created_by,
                )
            )

            old_due = due
            schedule.last_audit_engagement_id = engagement.id
            schedule.last_triggered_at = self.utcnow()
            schedule.next_due_date = self._advance_due_date(due, schedule.recurrence)
            schedule.next_audit_date = schedule.next_due_date

            AuditService(self.db).write_audit_log(
                action="audit_schedule.engagement_auto_created",
                entity_type="audit_schedule",
                entity_id=schedule.id,
                organization_id=schedule.organization_id,
                actor_user_id=None,
                metadata_json={
                    "schedule_id": str(schedule.id),
                    "engagement_id": str(engagement.id),
                    "next_due_date": old_due.isoformat(),
                },
            )
            created_count += 1

        self.db.flush()
        return created_count

    def get_schedule_history(self, org_id: uuid.UUID, schedule_id: uuid.UUID) -> list[AuditEngagement]:
        _ = self.require_schedule(org_id, schedule_id)
        return self.db.execute(
            select(AuditEngagement)
            .where(
                AuditEngagement.organization_id == org_id,
                AuditEngagement.source_schedule_id == schedule_id,
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
        row.is_active = False
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
                "is_active": row.is_active,
                "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
            },
            metadata_json={"source": "api"},
        )
        return row


def run_daily_audit_schedule_reminder_sweep(db: Session) -> dict[str, int]:
    # Fleet-wide by design: this is the scheduled job, which has no acting tenant.
    # HTTP callers must pass organization_id -- see process_schedule_reminders.
    return AuditScheduleService(db).process_schedule_reminders(organization_id=None)


def run_daily_scheduled_audit_creation_sweep(db: Session) -> dict[str, int]:
    created = AuditScheduleService(db).run_scheduled_audit_creation()
    return {"engagements_created": created, "records_processed": created}
