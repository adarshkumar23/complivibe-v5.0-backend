import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class FrameworkPackReviewAssignment(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "framework_pack_review_assignments"
    __table_args__ = (
        Index("ix_framework_pack_review_assignments_org_review", "organization_id", "review_run_id"),
        Index("ix_framework_pack_review_assignments_org_assignee_status", "organization_id", "assigned_to_user_id", "status"),
        Index("ix_framework_pack_review_assignments_org_due_at", "organization_id", "due_at"),
    )

    review_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("framework_pack_review_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    assigned_to_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    assigned_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="assigned")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
