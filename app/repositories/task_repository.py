import uuid
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.task import Task


class TaskRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, task_id: uuid.UUID) -> Task | None:
        return self.db.execute(select(Task).where(Task.id == task_id)).scalar_one_or_none()

    def list_by_organization(
        self,
        organization_id: uuid.UUID,
        *,
        status: str | None = None,
        priority: str | None = None,
        task_type: str | None = None,
        owner_user_id: uuid.UUID | None = None,
        linked_entity_type: str | None = None,
        linked_entity_id: uuid.UUID | None = None,
        overdue_only: bool = False,
        due_before: datetime | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Task]:
        stmt = select(Task).where(Task.organization_id == organization_id)
        if status:
            stmt = stmt.where(Task.status == status)
        if priority:
            stmt = stmt.where(Task.priority == priority)
        if task_type:
            stmt = stmt.where(Task.task_type == task_type)
        if owner_user_id:
            stmt = stmt.where(Task.owner_user_id == owner_user_id)
        if linked_entity_type:
            stmt = stmt.where(Task.linked_entity_type == linked_entity_type)
        if linked_entity_id:
            stmt = stmt.where(Task.linked_entity_id == linked_entity_id)
        if overdue_only:
            stmt = stmt.where(
                Task.status.in_(["open", "in_progress", "blocked"]),
                Task.due_date.is_not(None),
                Task.due_date < datetime.now(UTC),
            )
        if due_before:
            stmt = stmt.where(Task.due_date.is_not(None), Task.due_date <= due_before)
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(or_(Task.title.ilike(like), Task.description.ilike(like)))

        stmt = stmt.order_by(Task.created_at.desc()).offset(offset).limit(limit)
        return list(self.db.execute(stmt).scalars().all())
