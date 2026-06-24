import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Task(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_task_org_status", "organization_id", "status"),
        Index("ix_task_org_priority", "organization_id", "priority"),
        Index("ix_tasks_owner_id", "owner_id"),
        Index("ix_tasks_due_at", "due_at"),
        Index("ix_tasks_linked_entity", "organization_id", "linked_entity_type", "linked_entity_id"),
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="open")
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    task_type: Mapped[str] = mapped_column(String(32), nullable=False, default="general")
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        "owner_id",
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    due_date: Mapped[datetime | None] = mapped_column("due_at", DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    linked_entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    linked_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    reminder_status: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    last_reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
