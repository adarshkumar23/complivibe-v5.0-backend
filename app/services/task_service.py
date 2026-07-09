import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.evidence_item import EvidenceItem
from app.models.framework import Framework
from app.models.membership import Membership
from app.models.obligation import Obligation
from app.models.organization_framework import OrganizationFramework
from app.models.risk import Risk
from app.models.task import Task
from app.models.user import User
from app.models.control import Control
from app.services.email_service import EmailService


class TaskService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)

    def ensure_owner_is_active_member(self, organization_id: uuid.UUID, owner_user_id: uuid.UUID | None) -> User | None:
        if owner_user_id is None:
            return None

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
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task owner user not found")
        return user

    def validate_linked_entity(
        self,
        *,
        organization_id: uuid.UUID,
        linked_entity_type: str | None,
        linked_entity_id: uuid.UUID | None,
    ) -> dict | None:
        if linked_entity_type is None and linked_entity_id is None:
            return None
        if linked_entity_type is None or linked_entity_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="linked_entity_type and linked_entity_id must both be provided")

        if linked_entity_type == "risk":
            risk = self.db.execute(
                select(Risk).where(Risk.id == linked_entity_id, Risk.organization_id == organization_id)
            ).scalar_one_or_none()
            if risk is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked risk not found")
            return {"entity_type": "risk", "id": str(risk.id), "title": risk.title, "status": risk.status}

        if linked_entity_type == "control":
            control = self.db.execute(
                select(Control).where(Control.id == linked_entity_id, Control.organization_id == organization_id)
            ).scalar_one_or_none()
            if control is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked control not found")
            return {"entity_type": "control", "id": str(control.id), "title": control.title, "status": control.status}

        if linked_entity_type == "evidence":
            evidence = self.db.execute(
                select(EvidenceItem).where(EvidenceItem.id == linked_entity_id, EvidenceItem.organization_id == organization_id)
            ).scalar_one_or_none()
            if evidence is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked evidence not found")
            return {"entity_type": "evidence", "id": str(evidence.id), "title": evidence.title, "status": evidence.status}

        if linked_entity_type == "obligation":
            obligation = self.db.execute(select(Obligation).where(Obligation.id == linked_entity_id)).scalar_one_or_none()
            if obligation is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked obligation not found")
            org_framework = self.db.execute(
                select(OrganizationFramework).where(
                    OrganizationFramework.organization_id == organization_id,
                    OrganizationFramework.framework_id == obligation.framework_id,
                    OrganizationFramework.status == "active",
                )
            ).scalar_one_or_none()
            if org_framework is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Linked obligation framework is not active for organization")
            return {"entity_type": "obligation", "id": str(obligation.id), "title": obligation.title, "status": obligation.status}

        if linked_entity_type == "framework":
            framework = self.db.execute(select(Framework).where(Framework.id == linked_entity_id)).scalar_one_or_none()
            if framework is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked framework not found")
            return {"entity_type": "framework", "id": str(framework.id), "title": framework.name, "status": framework.status}

        if linked_entity_type == "organization_framework":
            org_framework = self.db.execute(
                select(OrganizationFramework).where(
                    OrganizationFramework.id == linked_entity_id,
                    OrganizationFramework.organization_id == organization_id,
                )
            ).scalar_one_or_none()
            if org_framework is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked organization framework not found")
            return {"entity_type": "organization_framework", "id": str(org_framework.id), "title": str(org_framework.framework_id), "status": org_framework.status}

        if linked_entity_type == "general":
            return {"entity_type": "general", "id": str(linked_entity_id), "title": "General", "status": "n/a"}

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported linked_entity_type")

    def queue_task_notification(
        self,
        *,
        organization_id: uuid.UUID,
        created_by_user_id: uuid.UUID,
        owner_user: User,
        task_title: str,
        template_key: str = "task_assigned",
        event_type: str = "task.assigned",
        priority: str = "normal",
        extra_variables: dict[str, str | int] | None = None,
    ) -> uuid.UUID:
        email = owner_user.email
        if not email:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assignee email is required for notification")

        email_service = EmailService(self.db)
        template = email_service.resolve_template_for_org(
            organization_id=organization_id,
            template_id=None,
            template_key=template_key,
        )
        variables: dict[str, str | int] = {
            "user_name": owner_user.full_name or owner_user.email,
            "task_title": task_title,
        }
        if extra_variables:
            variables.update(extra_variables)
        outbox = email_service.queue_email(
            organization_id=organization_id,
            template=template,
            event_type=event_type,
            recipient_email=email,
            recipient_user_id=owner_user.id,
            priority=priority,
            scheduled_at=None,
            metadata_json={"source": "task_workflow"},
            created_by_user_id=created_by_user_id,
            variables_json=variables,
            initial_status="pending",
        )
        return outbox.id

    @staticmethod
    def escalation_for_overdue_days(days_overdue: int) -> dict[str, str]:
        """Real escalation tiers for an overdue task reminder, keyed by how many whole
        days past due_date the task is. Used both for the email's priority/subject and
        for the task's own `escalation_tier` field, so an old, deeply overdue task
        actually looks urgent everywhere -- not stuck at "normal" forever -- without
        clobbering the task's user-set `priority`."""
        if days_overdue >= 14:
            return {
                "escalation_level": "critical",
                "escalation_label": "URGENT: Manager Escalation",
                "escalation_message": (
                    "This task is critically overdue and has been escalated. Please resolve immediately "
                    "or contact your manager if you are blocked."
                ),
                "priority": "urgent",
            }
        if days_overdue >= 3:
            return {
                "escalation_level": "firm",
                "escalation_label": "Second Reminder",
                "escalation_message": "This task is significantly overdue. Please complete it as soon as possible.",
                "priority": "high",
            }
        return {
            "escalation_level": "gentle",
            "escalation_label": "Reminder",
            "escalation_message": "This task is now overdue. Please complete it when you can.",
            "priority": "normal",
        }

    def summary(self, organization_id: uuid.UUID) -> dict[str, int]:
        now = self.now()
        due_soon_cutoff = now + timedelta(days=3)

        total_tasks = int(self.db.execute(select(func.count(Task.id)).where(Task.organization_id == organization_id)).scalar_one())

        status_counts: dict[str, int] = {}
        for status_name in ["open", "in_progress", "blocked", "completed", "cancelled"]:
            status_counts[status_name] = int(
                self.db.execute(
                    select(func.count(Task.id)).where(Task.organization_id == organization_id, Task.status == status_name)
                ).scalar_one()
            )

        overdue_tasks = int(
            self.db.execute(
                select(func.count(Task.id)).where(
                    Task.organization_id == organization_id,
                    Task.status.in_(["open", "in_progress", "blocked"]),
                    Task.due_date.is_not(None),
                    Task.due_date < now,
                )
            ).scalar_one()
        )

        due_soon_tasks = int(
            self.db.execute(
                select(func.count(Task.id)).where(
                    Task.organization_id == organization_id,
                    Task.status.in_(["open", "in_progress", "blocked"]),
                    Task.due_date.is_not(None),
                    Task.due_date >= now,
                    Task.due_date <= due_soon_cutoff,
                )
            ).scalar_one()
        )

        unassigned_tasks = int(
            self.db.execute(
                select(func.count(Task.id)).where(
                    Task.organization_id == organization_id,
                    Task.owner_user_id.is_(None),
                    Task.status.in_(["open", "in_progress", "blocked"]),
                )
            ).scalar_one()
        )

        urgent_open_tasks = int(
            self.db.execute(
                select(func.count(Task.id)).where(
                    Task.organization_id == organization_id,
                    Task.priority == "urgent",
                    Task.status.in_(["open", "in_progress", "blocked"]),
                )
            ).scalar_one()
        )

        return {
            "total_tasks": total_tasks,
            "open_tasks": status_counts["open"],
            "in_progress_tasks": status_counts["in_progress"],
            "blocked_tasks": status_counts["blocked"],
            "completed_tasks": status_counts["completed"],
            "cancelled_tasks": status_counts["cancelled"],
            "overdue_tasks": overdue_tasks,
            "due_soon_tasks": due_soon_tasks,
            "unassigned_tasks": unassigned_tasks,
            "urgent_open_tasks": urgent_open_tasks,
        }
