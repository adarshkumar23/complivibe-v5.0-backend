import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class FrameworkReviewBatchAssignmentItem(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "framework_review_batch_assignment_items"
    __table_args__ = (
        Index("ix_framework_review_batch_assignment_items_org_run", "organization_id", "batch_run_id"),
        Index("ix_framework_review_batch_assignment_items_org_status", "organization_id", "status"),
        Index(
            "ix_framework_review_batch_assignment_items_org_review_assignee",
            "organization_id",
            "review_run_id",
            "assigned_to_user_id",
        ),
    )

    batch_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("framework_review_batch_assignment_runs.id", ondelete="CASCADE"),
        nullable=False,
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
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    created_assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("framework_pack_review_assignments.id", ondelete="SET NULL"),
        nullable=True,
    )
    skipped_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    scoring_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
