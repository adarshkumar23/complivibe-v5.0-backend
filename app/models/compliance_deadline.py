import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ComplianceDeadline(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "compliance_deadlines"
    __table_args__ = (
        Index("ix_compliance_deadlines_org_status", "organization_id", "status"),
        Index("ix_compliance_deadlines_org_type", "organization_id", "deadline_type"),
        Index("ix_compliance_deadlines_org_priority", "organization_id", "priority"),
        Index("ix_compliance_deadlines_org_owner", "organization_id", "owner_user_id"),
        Index("ix_compliance_deadlines_org_due_date", "organization_id", "due_date"),
        Index("ix_compliance_deadlines_org_linked", "organization_id", "linked_entity_type", "linked_entity_id"),
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    deadline_type: Mapped[str] = mapped_column(String(64), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="upcoming")
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    linked_entity_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    linked_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)

    reminder_days_before: Mapped[int] = mapped_column(nullable=False, default=7)
    last_reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    completion_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    waiver_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    tags_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
