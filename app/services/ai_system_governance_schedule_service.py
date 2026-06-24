import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ai_system import AISystem
from app.models.ai_system_governance_review import AISystemGovernanceReview
from app.models.ai_system_governance_review_event import AISystemGovernanceReviewEvent
from app.models.ai_system_governance_review_reminder_policy import AISystemGovernanceReviewReminderPolicy
from app.models.email_outbox import EmailOutbox
from app.models.user import User
from app.services.email_service import EmailService
from app.services.seed_service import SeedService


class AISystemGovernanceScheduleService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def ensure_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def validate_non_negative(field_name: str, value: int) -> None:
        if value < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_name} must be non-negative")

    def require_reminder_policy(
        self,
        *,
        organization_id: uuid.UUID,
        policy_id: uuid.UUID,
    ) -> AISystemGovernanceReviewReminderPolicy:
        row = self.db.execute(
            select(AISystemGovernanceReviewReminderPolicy).where(
                AISystemGovernanceReviewReminderPolicy.id == policy_id,
                AISystemGovernanceReviewReminderPolicy.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI governance review reminder policy not found")
        return row

    def require_event(
        self,
        *,
        organization_id: uuid.UUID,
        event_id: uuid.UUID,
    ) -> AISystemGovernanceReviewEvent:
        row = self.db.execute(
            select(AISystemGovernanceReviewEvent).where(
                AISystemGovernanceReviewEvent.id == event_id,
                AISystemGovernanceReviewEvent.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI governance review event not found")
        return row

    def create_reminder_policy(
        self,
        *,
        organization_id: uuid.UUID,
        name: str,
        review_type: str | None,
        days_before_due: int,
        overdue_after_days: int,
        escalation_after_days: int,
        notify_assignee: bool,
        status_value: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceReviewReminderPolicy:
        self.validate_non_negative("days_before_due", days_before_due)
        self.validate_non_negative("overdue_after_days", overdue_after_days)
        self.validate_non_negative("escalation_after_days", escalation_after_days)
        row = AISystemGovernanceReviewReminderPolicy(
            organization_id=organization_id,
            name=name,
            review_type=review_type,
            days_before_due=days_before_due,
            overdue_after_days=overdue_after_days,
            escalation_after_days=escalation_after_days,
            notify_assignee=notify_assignee,
            status=status_value,
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_reminder_policies(self, *, organization_id: uuid.UUID) -> list[AISystemGovernanceReviewReminderPolicy]:
        return (
            self.db.execute(
                select(AISystemGovernanceReviewReminderPolicy)
                .where(AISystemGovernanceReviewReminderPolicy.organization_id == organization_id)
                .order_by(AISystemGovernanceReviewReminderPolicy.created_at.desc())
            )
            .scalars()
            .all()
        )

    def update_reminder_policy(
        self,
        *,
        row: AISystemGovernanceReviewReminderPolicy,
        name: str | None = None,
        review_type: str | None = None,
        days_before_due: int | None = None,
        overdue_after_days: int | None = None,
        escalation_after_days: int | None = None,
        notify_assignee: bool | None = None,
        status_value: str | None = None,
    ) -> AISystemGovernanceReviewReminderPolicy:
        if name is not None:
            row.name = name
        if review_type is not None:
            row.review_type = review_type
        if days_before_due is not None:
            self.validate_non_negative("days_before_due", days_before_due)
            row.days_before_due = days_before_due
        if overdue_after_days is not None:
            self.validate_non_negative("overdue_after_days", overdue_after_days)
            row.overdue_after_days = overdue_after_days
        if escalation_after_days is not None:
            self.validate_non_negative("escalation_after_days", escalation_after_days)
            row.escalation_after_days = escalation_after_days
        if notify_assignee is not None:
            row.notify_assignee = notify_assignee
        if status_value is not None:
            row.status = status_value
        self.db.flush()
        return row

    def archive_reminder_policy(self, *, row: AISystemGovernanceReviewReminderPolicy) -> AISystemGovernanceReviewReminderPolicy:
        row.status = "archived"
        self.db.flush()
        return row

    def get_policy_for_review(
        self,
        *,
        organization_id: uuid.UUID,
        review: AISystemGovernanceReview,
    ) -> AISystemGovernanceReviewReminderPolicy | None:
        if review.reminder_policy_id is not None:
            row = self.db.execute(
                select(AISystemGovernanceReviewReminderPolicy).where(
                    AISystemGovernanceReviewReminderPolicy.id == review.reminder_policy_id,
                    AISystemGovernanceReviewReminderPolicy.organization_id == organization_id,
                    AISystemGovernanceReviewReminderPolicy.status == "active",
                )
            ).scalar_one_or_none()
            if row is not None:
                return row

        type_specific = self.db.execute(
            select(AISystemGovernanceReviewReminderPolicy)
            .where(
                AISystemGovernanceReviewReminderPolicy.organization_id == organization_id,
                AISystemGovernanceReviewReminderPolicy.status == "active",
                AISystemGovernanceReviewReminderPolicy.review_type == review.review_type,
            )
            .order_by(AISystemGovernanceReviewReminderPolicy.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if type_specific is not None:
            return type_specific

        return self.db.execute(
            select(AISystemGovernanceReviewReminderPolicy)
            .where(
                AISystemGovernanceReviewReminderPolicy.organization_id == organization_id,
                AISystemGovernanceReviewReminderPolicy.status == "active",
                AISystemGovernanceReviewReminderPolicy.review_type.is_(None),
            )
            .order_by(AISystemGovernanceReviewReminderPolicy.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    def queue_items(
        self,
        *,
        organization_id: uuid.UUID,
        status_filter: str | None,
        review_type: str | None,
        overdue_only: bool,
        due_before: datetime | None,
        assigned_to_user_id: uuid.UUID | None,
        ai_system_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        now = self.now()
        due_before_utc = self.ensure_utc(due_before) if due_before is not None else None
        stmt = (
            select(AISystemGovernanceReview)
            .where(
                AISystemGovernanceReview.organization_id == organization_id,
                AISystemGovernanceReview.due_at.is_not(None),
                AISystemGovernanceReview.status.in_(["pending", "in_progress"]),
            )
            .order_by(AISystemGovernanceReview.due_at.asc(), AISystemGovernanceReview.created_at.asc())
        )

        if status_filter:
            stmt = stmt.where(AISystemGovernanceReview.status == status_filter)
        if review_type:
            stmt = stmt.where(AISystemGovernanceReview.review_type == review_type)
        if assigned_to_user_id:
            stmt = stmt.where(AISystemGovernanceReview.assigned_to_user_id == assigned_to_user_id)
        if ai_system_id:
            stmt = stmt.where(AISystemGovernanceReview.ai_system_id == ai_system_id)
        if due_before_utc:
            stmt = stmt.where(AISystemGovernanceReview.due_at <= due_before_utc)

        rows = self.db.execute(stmt).scalars().all()
        items: list[dict[str, Any]] = []
        for row in rows:
            due_at = self.ensure_utc(row.due_at)
            policy = self.get_policy_for_review(organization_id=organization_id, review=row)
            days_before_due = policy.days_before_due if policy is not None else 0
            overdue_after_days = policy.overdue_after_days if policy is not None else 0
            escalation_after_days = policy.escalation_after_days if policy is not None else 0

            reminder_due_at = due_at - timedelta(days=days_before_due)
            overdue_at = due_at + timedelta(days=overdue_after_days)
            escalation_at = due_at + timedelta(days=escalation_after_days)

            is_due_soon = reminder_due_at <= now <= due_at
            is_overdue = now > overdue_at
            is_escalation_due = now > escalation_at

            if overdue_only and not is_overdue:
                continue

            items.append(
                {
                    "review_id": row.id,
                    "ai_system_id": row.ai_system_id,
                    "review_type": row.review_type,
                    "status": row.status,
                    "title": row.title,
                    "assigned_to_user_id": row.assigned_to_user_id,
                    "due_at": due_at,
                    "reminder_policy_id": policy.id if policy is not None else row.reminder_policy_id,
                    "reminder_policy_name": policy.name if policy is not None else None,
                    "days_before_due": days_before_due,
                    "overdue_after_days": overdue_after_days,
                    "escalation_after_days": escalation_after_days,
                    "reminder_due_at": reminder_due_at,
                    "overdue_at": overdue_at,
                    "escalation_at": escalation_at,
                    "is_due_soon": is_due_soon,
                    "is_overdue": is_overdue,
                    "is_escalation_due": is_escalation_due,
                    "last_reminder_at": row.last_reminder_at,
                    "escalated_at": row.escalated_at,
                }
            )

        return items[offset : offset + limit]

    def _find_open_event(
        self,
        *,
        organization_id: uuid.UUID,
        review_id: uuid.UUID,
        event_type: str,
    ) -> AISystemGovernanceReviewEvent | None:
        return self.db.execute(
            select(AISystemGovernanceReviewEvent).where(
                AISystemGovernanceReviewEvent.organization_id == organization_id,
                AISystemGovernanceReviewEvent.review_id == review_id,
                AISystemGovernanceReviewEvent.event_type == event_type,
                AISystemGovernanceReviewEvent.status == "open",
            )
        ).scalar_one_or_none()

    def _create_event(
        self,
        *,
        organization_id: uuid.UUID,
        ai_system_id: uuid.UUID,
        review_id: uuid.UUID,
        event_type: str,
        details_json: dict,
    ) -> AISystemGovernanceReviewEvent:
        row = AISystemGovernanceReviewEvent(
            organization_id=organization_id,
            ai_system_id=ai_system_id,
            review_id=review_id,
            event_type=event_type,
            status="open",
            triggered_at=self.now(),
            details_json=details_json,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _queue_reminder_email(
        self,
        *,
        organization_id: uuid.UUID,
        review: AISystemGovernanceReview,
        ai_system: AISystem,
        actor_user_id: uuid.UUID,
    ) -> uuid.UUID | None:
        if review.assigned_to_user_id is None:
            return None
        assignee = self.db.execute(select(User).where(User.id == review.assigned_to_user_id)).scalar_one_or_none()
        if assignee is None or not assignee.email:
            return None

        SeedService.ensure_global_email_templates(self.db)
        template = EmailService(self.db).resolve_template_for_org(
            organization_id=organization_id,
            template_id=None,
            template_key="task_assigned",
        )
        outbox = EmailService(self.db).queue_email(
            organization_id=organization_id,
            template=template,
            event_type="ai_system.governance_review.reminder",
            recipient_email=assignee.email,
            recipient_user_id=assignee.id,
            priority="normal",
            scheduled_at=None,
            metadata_json={"source": "ai_system_governance_review_schedule"},
            created_by_user_id=actor_user_id,
            variables_json={
                "user_name": assignee.full_name or assignee.email,
                "task_title": f"AI governance review {review.title} for {ai_system.name} due {self.ensure_utc(review.due_at).isoformat()}",
            },
            initial_status="pending",
        )
        return outbox.id

    def evaluate_schedules(
        self,
        *,
        organization_id: uuid.UUID,
        dry_run: bool,
        notify: bool,
        actor_user_id: uuid.UUID,
    ) -> dict[str, Any]:
        now = self.now()
        reviews = (
            self.db.execute(
                select(AISystemGovernanceReview).where(
                    AISystemGovernanceReview.organization_id == organization_id,
                    AISystemGovernanceReview.status.in_(["pending", "in_progress"]),
                    AISystemGovernanceReview.due_at.is_not(None),
                )
            )
            .scalars()
            .all()
        )

        ai_system_ids = {row.ai_system_id for row in reviews}
        ai_systems = {
            row.id: row
            for row in self.db.execute(
                select(AISystem).where(
                    AISystem.organization_id == organization_id,
                    AISystem.id.in_(ai_system_ids) if ai_system_ids else False,
                )
            )
            .scalars()
            .all()
        }

        would_create: list[dict[str, Any]] = []
        created_events: list[AISystemGovernanceReviewEvent] = []
        queued_email_ids: list[str] = []

        for review in reviews:
            due_at = self.ensure_utc(review.due_at)
            policy = self.get_policy_for_review(organization_id=organization_id, review=review)
            days_before_due = policy.days_before_due if policy is not None else 0
            overdue_after_days = policy.overdue_after_days if policy is not None else 0
            escalation_after_days = policy.escalation_after_days if policy is not None else 0

            reminder_due_at = due_at - timedelta(days=days_before_due)
            overdue_at = due_at + timedelta(days=overdue_after_days)
            escalation_at = due_at + timedelta(days=escalation_after_days)

            reminder_due = reminder_due_at <= now <= due_at and review.last_reminder_at is None
            overdue_due = now > overdue_at
            escalation_due = now > escalation_at

            checks = [
                ("reminder_due", reminder_due, reminder_due_at),
                ("review_overdue", overdue_due, overdue_at),
                ("escalation_due", escalation_due, escalation_at),
            ]

            for event_type, due_flag, threshold_at in checks:
                if not due_flag:
                    continue
                payload = {
                    "event_type": event_type,
                    "review_id": str(review.id),
                    "ai_system_id": str(review.ai_system_id),
                    "due_at": due_at.isoformat(),
                    "threshold_at": threshold_at.isoformat(),
                }

                existing_open = self._find_open_event(
                    organization_id=organization_id,
                    review_id=review.id,
                    event_type=event_type,
                )
                if existing_open is not None:
                    continue

                if dry_run:
                    would_create.append(payload)
                    continue

                event = self._create_event(
                    organization_id=organization_id,
                    ai_system_id=review.ai_system_id,
                    review_id=review.id,
                    event_type=event_type,
                    details_json=payload,
                )
                created_events.append(event)

                if event_type == "reminder_due":
                    review.last_reminder_at = now
                    if notify and policy is not None and policy.notify_assignee:
                        ai_system = ai_systems.get(review.ai_system_id)
                        if ai_system is not None:
                            email_id = self._queue_reminder_email(
                                organization_id=organization_id,
                                review=review,
                                ai_system=ai_system,
                                actor_user_id=actor_user_id,
                            )
                            if email_id is not None:
                                queued_email_ids.append(str(email_id))

                if event_type == "escalation_due":
                    review.escalated_at = now

        if not dry_run:
            self.db.flush()

        return {
            "dry_run": dry_run,
            "would_create_count": len(would_create),
            "created_count": 0 if dry_run else len(created_events),
            "queued_email_count": 0 if dry_run else len(queued_email_ids),
            "would_create": would_create,
            "created_event_ids": [] if dry_run else [str(row.id) for row in created_events],
            "queued_email_ids": [] if dry_run else queued_email_ids,
        }

    def list_events(
        self,
        *,
        organization_id: uuid.UUID,
        event_type: str | None,
        status_filter: str | None,
        review_id: uuid.UUID | None,
        ai_system_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> list[AISystemGovernanceReviewEvent]:
        stmt = select(AISystemGovernanceReviewEvent).where(AISystemGovernanceReviewEvent.organization_id == organization_id)
        if event_type:
            stmt = stmt.where(AISystemGovernanceReviewEvent.event_type == event_type)
        if status_filter:
            stmt = stmt.where(AISystemGovernanceReviewEvent.status == status_filter)
        if review_id:
            stmt = stmt.where(AISystemGovernanceReviewEvent.review_id == review_id)
        if ai_system_id:
            stmt = stmt.where(AISystemGovernanceReviewEvent.ai_system_id == ai_system_id)
        return (
            self.db.execute(
                stmt.order_by(AISystemGovernanceReviewEvent.triggered_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )

    def resolve_event(
        self,
        *,
        row: AISystemGovernanceReviewEvent,
        actor_user_id: uuid.UUID,
        resolution_notes: str | None,
    ) -> AISystemGovernanceReviewEvent:
        if row.status != "open":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI governance review event is not open")
        row.status = "resolved"
        row.resolved_at = self.now()
        row.resolved_by_user_id = actor_user_id
        row.resolution_notes = resolution_notes
        self.db.flush()
        return row

    def schedule_summary(self, *, organization_id: uuid.UUID) -> dict[str, int | dict[str, int]]:
        now = self.now()
        reviews = (
            self.db.execute(
                select(AISystemGovernanceReview).where(
                    AISystemGovernanceReview.organization_id == organization_id,
                    AISystemGovernanceReview.status.in_(["pending", "in_progress"]),
                )
            )
            .scalars()
            .all()
        )

        scheduled_reviews = [row for row in reviews if row.due_at is not None]
        unscheduled_reviews = len(reviews) - len(scheduled_reviews)

        due_soon_reviews = 0
        overdue_reviews = 0
        escalated_reviews = 0

        open_escalated_review_ids = {
            row.review_id
            for row in self.db.execute(
                select(AISystemGovernanceReviewEvent).where(
                    AISystemGovernanceReviewEvent.organization_id == organization_id,
                    AISystemGovernanceReviewEvent.status == "open",
                    AISystemGovernanceReviewEvent.event_type == "escalation_due",
                )
            )
            .scalars()
            .all()
        }

        for row in scheduled_reviews:
            due_at = self.ensure_utc(row.due_at)
            policy = self.get_policy_for_review(organization_id=organization_id, review=row)
            days_before_due = policy.days_before_due if policy is not None else 0
            overdue_after_days = policy.overdue_after_days if policy is not None else 0
            escalation_after_days = policy.escalation_after_days if policy is not None else 0

            reminder_due_at = due_at - timedelta(days=days_before_due)
            overdue_at = due_at + timedelta(days=overdue_after_days)
            escalation_at = due_at + timedelta(days=escalation_after_days)

            if reminder_due_at <= now <= due_at:
                due_soon_reviews += 1
            if now > overdue_at:
                overdue_reviews += 1
            if row.escalated_at is not None or row.id in open_escalated_review_ids or now > escalation_at:
                escalated_reviews += 1

        events = (
            self.db.execute(select(AISystemGovernanceReviewEvent).where(AISystemGovernanceReviewEvent.organization_id == organization_id))
            .scalars()
            .all()
        )

        by_event_type_rows = self.db.execute(
            select(AISystemGovernanceReviewEvent.event_type, func.count(AISystemGovernanceReviewEvent.id))
            .where(AISystemGovernanceReviewEvent.organization_id == organization_id)
            .group_by(AISystemGovernanceReviewEvent.event_type)
        ).all()

        return {
            "scheduled_reviews": len(scheduled_reviews),
            "unscheduled_reviews": unscheduled_reviews,
            "due_soon_reviews": due_soon_reviews,
            "overdue_reviews": overdue_reviews,
            "escalated_reviews": escalated_reviews,
            "open_events": len([row for row in events if row.status == "open"]),
            "resolved_events": len([row for row in events if row.status == "resolved"]),
            "by_event_type": {str(key): int(count) for key, count in by_event_type_rows if key is not None},
        }

    def queued_outbox_count(self, *, organization_id: uuid.UUID) -> int:
        return int(
            self.db.execute(
                select(func.count(EmailOutbox.id)).where(
                    EmailOutbox.organization_id == organization_id,
                    EmailOutbox.event_type == "ai_system.governance_review.reminder",
                )
            ).scalar_one()
        )
