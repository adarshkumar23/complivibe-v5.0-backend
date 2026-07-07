import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.compliance_deadline import ComplianceDeadline
from app.models.compliance_deadline_event import ComplianceDeadlineEvent
from app.models.compliance_policy import CompliancePolicy
from app.models.control import Control
from app.models.evidence_item import EvidenceItem
from app.models.framework import Framework
from app.models.membership import Membership
from app.models.task import Task
from app.models.user import User
from app.models.vendor import Vendor
from app.services.email_service import EmailService
from app.services.seed_service import SeedService

TERMINAL_STATUSES = {"completed", "waived", "cancelled"}


class ComplianceDeadlineService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def utcdate() -> date:
        return datetime.now(UTC).date()

    def require_deadline_in_org(self, organization_id: uuid.UUID, deadline_id: uuid.UUID) -> ComplianceDeadline:
        row = self.db.execute(
            select(ComplianceDeadline).where(
                ComplianceDeadline.id == deadline_id,
                ComplianceDeadline.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compliance deadline not found")
        return row

    def require_event_in_org(self, organization_id: uuid.UUID, event_id: uuid.UUID) -> ComplianceDeadlineEvent:
        row = self.db.execute(
            select(ComplianceDeadlineEvent).where(
                ComplianceDeadlineEvent.id == event_id,
                ComplianceDeadlineEvent.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compliance deadline event not found")
        return row

    def ensure_owner_is_active_member(self, organization_id: uuid.UUID, owner_user_id: uuid.UUID) -> User:
        membership = self.db.execute(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.user_id == owner_user_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="owner_user_id must be an active member of the organization",
            )

        user = self.db.execute(select(User).where(User.id == owner_user_id)).scalar_one_or_none()
        if user is None or not user.is_active or user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="owner_user_id must be an active member of the organization",
            )
        return user

    def owner_activity_map(self, organization_id: uuid.UUID, owner_user_ids: set[uuid.UUID]) -> dict[uuid.UUID, bool]:
        if not owner_user_ids:
            return {}
        active_owner_rows = self.db.execute(
            select(Membership.user_id)
            .join(User, User.id == Membership.user_id)
            .where(
                Membership.organization_id == organization_id,
                Membership.status == "active",
                Membership.user_id.in_(owner_user_ids),
                User.is_active.is_(True),
                User.status == "active",
            )
        ).scalars().all()
        active_owner_ids = set(active_owner_rows)
        return {owner_id: owner_id in active_owner_ids for owner_id in owner_user_ids}

    def deadline_context(
        self,
        deadline: ComplianceDeadline,
        *,
        owner_is_active: bool = True,
        today: date | None = None,
    ) -> dict[str, int | str | bool | list[str] | None]:
        evaluated_date = today or self.utcdate()
        days_until_due = (deadline.due_date - evaluated_date).days
        recommended_status: str | None = None
        is_status_stale = False
        context_flags: list[str] = []

        if deadline.status == "upcoming" and deadline.due_date < evaluated_date:
            recommended_status = "overdue"
            is_status_stale = True
            context_flags.append("past_due_not_marked_overdue")
        elif deadline.status == "overdue" and deadline.due_date >= evaluated_date:
            recommended_status = "upcoming"
            is_status_stale = True
            context_flags.append("overdue_status_but_not_past_due")

        if deadline.status in {"upcoming", "overdue"} and days_until_due <= 7:
            context_flags.append("due_within_7_days")
        if deadline.status in {"upcoming", "overdue"} and days_until_due < 0:
            context_flags.append("past_due")
        if not owner_is_active:
            context_flags.append("owner_inactive_or_unassigned")
        if (
            deadline.status == "upcoming"
            and deadline.last_reminder_at is None
            and deadline.due_date >= evaluated_date
            and evaluated_date >= (deadline.due_date - timedelta(days=max(0, deadline.reminder_days_before)))
        ):
            context_flags.append("reminder_window_open_without_reminder")

        return {
            "days_until_due": days_until_due,
            "recommended_status": recommended_status,
            "is_status_stale": is_status_stale,
            "context_flags": context_flags,
        }

    def validate_linked_entity(
        self,
        *,
        organization_id: uuid.UUID,
        linked_entity_type: str | None,
        linked_entity_id: uuid.UUID | None,
    ) -> None:
        if linked_entity_type is None and linked_entity_id is None:
            return
        if linked_entity_type is None or linked_entity_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="linked_entity_type and linked_entity_id must both be provided")

        if linked_entity_type == "control":
            exists = self.db.execute(
                select(Control.id).where(Control.organization_id == organization_id, Control.id == linked_entity_id)
            ).scalar_one_or_none()
            if exists is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked control not found")
            return

        if linked_entity_type == "evidence":
            exists = self.db.execute(
                select(EvidenceItem.id).where(EvidenceItem.organization_id == organization_id, EvidenceItem.id == linked_entity_id)
            ).scalar_one_or_none()
            if exists is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked evidence not found")
            return

        if linked_entity_type == "policy":
            exists = self.db.execute(
                select(CompliancePolicy.id).where(CompliancePolicy.organization_id == organization_id, CompliancePolicy.id == linked_entity_id)
            ).scalar_one_or_none()
            if exists is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked policy not found")
            return

        if linked_entity_type == "vendor":
            exists = self.db.execute(
                select(Vendor.id).where(Vendor.organization_id == organization_id, Vendor.id == linked_entity_id)
            ).scalar_one_or_none()
            if exists is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked vendor not found")
            return

        if linked_entity_type == "framework":
            exists = self.db.execute(select(Framework.id).where(Framework.id == linked_entity_id)).scalar_one_or_none()
            if exists is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked framework not found")
            return

        if linked_entity_type == "task":
            exists = self.db.execute(
                select(Task.id).where(Task.organization_id == organization_id, Task.id == linked_entity_id)
            ).scalar_one_or_none()
            if exists is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked task not found")
            return

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported linked_entity_type")

    @staticmethod
    def ensure_not_terminal(deadline: ComplianceDeadline) -> None:
        if deadline.status in TERMINAL_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Completed, waived, or cancelled deadlines are terminal",
            )

    def has_same_day_event(self, organization_id: uuid.UUID, deadline_id: uuid.UUID, event_type: str, now: datetime) -> bool:
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        existing = self.db.execute(
            select(ComplianceDeadlineEvent.id).where(
                ComplianceDeadlineEvent.organization_id == organization_id,
                ComplianceDeadlineEvent.deadline_id == deadline_id,
                ComplianceDeadlineEvent.event_type == event_type,
                ComplianceDeadlineEvent.created_at >= day_start,
                ComplianceDeadlineEvent.created_at < day_end,
            )
        ).scalar_one_or_none()
        return existing is not None

    def queue_deadline_reminder(self, *, organization_id: uuid.UUID, owner_user: User, deadline: ComplianceDeadline, actor_user_id: uuid.UUID) -> uuid.UUID | None:
        if not owner_user.email:
            return None
        SeedService.ensure_global_email_templates(self.db)
        email_service = EmailService(self.db)
        template = email_service.resolve_template_for_org(
            organization_id=organization_id,
            template_id=None,
            template_key="task_assigned",
        )
        outbox = email_service.queue_email(
            organization_id=organization_id,
            template=template,
            event_type="compliance.deadline.reminder",
            recipient_email=owner_user.email,
            recipient_user_id=owner_user.id,
            priority="normal",
            scheduled_at=None,
            metadata_json={"source": "compliance_deadline_workflow", "deadline_id": str(deadline.id)},
            created_by_user_id=actor_user_id,
            variables_json={
                "user_name": owner_user.full_name or owner_user.email,
                "task_title": deadline.title,
            },
            initial_status="pending",
        )
        return outbox.id

    def evaluate_due(self, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID, dry_run: bool) -> dict[str, int]:
        today = self.utcdate()
        now = self.utcnow()

        deadlines = self.db.execute(
            select(ComplianceDeadline).where(
                ComplianceDeadline.organization_id == organization_id,
                ComplianceDeadline.status.in_(["upcoming", "overdue"]),
            )
        ).scalars().all()

        overdue_marked = 0
        reminders_triggered = 0
        events_created = 0
        events_skipped_duplicates = 0

        for deadline in deadlines:
            owner_user = self.db.execute(select(User).where(User.id == deadline.owner_user_id)).scalar_one_or_none()
            if owner_user is None:
                continue

            # upcoming -> overdue
            if deadline.status == "upcoming" and deadline.due_date < today:
                event_type = "overdue_detected"
                if self.has_same_day_event(organization_id, deadline.id, event_type, now):
                    events_skipped_duplicates += 1
                else:
                    outbox_queued = False
                    outbox_id: str | None = None
                    if not dry_run:
                        deadline.status = "overdue"
                        queued = self.queue_deadline_reminder(
                            organization_id=organization_id,
                            owner_user=owner_user,
                            deadline=deadline,
                            actor_user_id=actor_user_id,
                        )
                        if queued is not None:
                            outbox_queued = True
                            outbox_id = str(queued)
                    event = ComplianceDeadlineEvent(
                        organization_id=organization_id,
                        deadline_id=deadline.id,
                        event_type=event_type,
                        dry_run=dry_run,
                        outbox_queued=outbox_queued,
                        event_metadata_json={"status_transition": "upcoming_to_overdue", "outbox_id": outbox_id},
                    )
                    self.db.add(event)
                    events_created += 1
                    overdue_marked += 1

            # reminder window for upcoming deadlines only
            if deadline.status == "upcoming":
                remind_date = deadline.due_date - timedelta(days=max(0, deadline.reminder_days_before))
                if today >= remind_date and today <= deadline.due_date:
                    event_type = "reminder_due"
                    if self.has_same_day_event(organization_id, deadline.id, event_type, now):
                        events_skipped_duplicates += 1
                    else:
                        outbox_queued = False
                        outbox_id: str | None = None
                        if not dry_run:
                            queued = self.queue_deadline_reminder(
                                organization_id=organization_id,
                                owner_user=owner_user,
                                deadline=deadline,
                                actor_user_id=actor_user_id,
                            )
                            if queued is not None:
                                outbox_queued = True
                                outbox_id = str(queued)
                            deadline.last_reminder_at = now
                        event = ComplianceDeadlineEvent(
                            organization_id=organization_id,
                            deadline_id=deadline.id,
                            event_type=event_type,
                            dry_run=dry_run,
                            outbox_queued=outbox_queued,
                            event_metadata_json={"window_start": str(remind_date), "window_end": str(deadline.due_date), "outbox_id": outbox_id},
                        )
                        self.db.add(event)
                        events_created += 1
                        reminders_triggered += 1

        return {
            "deadlines_evaluated": len(deadlines),
            "overdue_marked": overdue_marked,
            "reminders_triggered": reminders_triggered,
            "events_created": events_created,
            "events_skipped_duplicates": events_skipped_duplicates,
        }

    def summary(self, organization_id: uuid.UUID) -> dict[str, int | dict[str, int]]:
        today = self.utcdate()
        seven_days = today + timedelta(days=7)

        total_deadlines = int(
            self.db.execute(select(func.count(ComplianceDeadline.id)).where(ComplianceDeadline.organization_id == organization_id)).scalar_one()
        )
        upcoming_deadlines = int(
            self.db.execute(select(func.count(ComplianceDeadline.id)).where(ComplianceDeadline.organization_id == organization_id, ComplianceDeadline.status == "upcoming")).scalar_one()
        )
        overdue_deadlines = int(
            self.db.execute(select(func.count(ComplianceDeadline.id)).where(ComplianceDeadline.organization_id == organization_id, ComplianceDeadline.status == "overdue")).scalar_one()
        )
        completed_deadlines = int(
            self.db.execute(select(func.count(ComplianceDeadline.id)).where(ComplianceDeadline.organization_id == organization_id, ComplianceDeadline.status == "completed")).scalar_one()
        )
        waived_deadlines = int(
            self.db.execute(select(func.count(ComplianceDeadline.id)).where(ComplianceDeadline.organization_id == organization_id, ComplianceDeadline.status == "waived")).scalar_one()
        )
        cancelled_deadlines = int(
            self.db.execute(select(func.count(ComplianceDeadline.id)).where(ComplianceDeadline.organization_id == organization_id, ComplianceDeadline.status == "cancelled")).scalar_one()
        )

        due_within_7_days = int(
            self.db.execute(
                select(func.count(ComplianceDeadline.id)).where(
                    ComplianceDeadline.organization_id == organization_id,
                    ComplianceDeadline.status.in_(["upcoming", "overdue"]),
                    ComplianceDeadline.due_date >= today,
                    ComplianceDeadline.due_date <= seven_days,
                )
            ).scalar_one()
        )

        high_risk_overdue_count = int(
            self.db.execute(
                select(func.count(ComplianceDeadline.id)).where(
                    ComplianceDeadline.organization_id == organization_id,
                    ComplianceDeadline.status == "overdue",
                    ComplianceDeadline.priority.in_(["critical", "high"]),
                )
            ).scalar_one()
        )

        live_deadlines = self.db.execute(
            select(ComplianceDeadline).where(
                ComplianceDeadline.organization_id == organization_id,
                ComplianceDeadline.status.in_(["upcoming", "overdue"]),
            )
        ).scalars().all()
        owner_map = self.owner_activity_map(organization_id, {row.owner_user_id for row in live_deadlines})
        stale_status_count = 0
        deadlines_without_active_owner = 0
        for row in live_deadlines:
            context = self.deadline_context(
                row,
                owner_is_active=owner_map.get(row.owner_user_id, False),
                today=today,
            )
            if context["is_status_stale"]:
                stale_status_count += 1
            if "owner_inactive_or_unassigned" in context["context_flags"]:
                deadlines_without_active_owner += 1

        by_status_rows = self.db.execute(
            select(ComplianceDeadline.status, func.count(ComplianceDeadline.id))
            .where(ComplianceDeadline.organization_id == organization_id)
            .group_by(ComplianceDeadline.status)
        ).all()
        by_deadline_type_rows = self.db.execute(
            select(ComplianceDeadline.deadline_type, func.count(ComplianceDeadline.id))
            .where(ComplianceDeadline.organization_id == organization_id)
            .group_by(ComplianceDeadline.deadline_type)
        ).all()
        by_priority_rows = self.db.execute(
            select(ComplianceDeadline.priority, func.count(ComplianceDeadline.id))
            .where(ComplianceDeadline.organization_id == organization_id)
            .group_by(ComplianceDeadline.priority)
        ).all()

        return {
            "total_deadlines": total_deadlines,
            "upcoming_deadlines": upcoming_deadlines,
            "overdue_deadlines": overdue_deadlines,
            "completed_deadlines": completed_deadlines,
            "waived_deadlines": waived_deadlines,
            "cancelled_deadlines": cancelled_deadlines,
            "due_within_7_days": due_within_7_days,
            "high_risk_overdue_count": high_risk_overdue_count,
            "stale_status_count": stale_status_count,
            "deadlines_without_active_owner": deadlines_without_active_owner,
            "by_status": {str(key): int(value) for key, value in by_status_rows},
            "by_deadline_type": {str(key): int(value) for key, value in by_deadline_type_rows},
            "by_priority": {str(key): int(value) for key, value in by_priority_rows},
        }
