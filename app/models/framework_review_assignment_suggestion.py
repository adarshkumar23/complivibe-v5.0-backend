import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class FrameworkReviewAssignmentSuggestion(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "framework_review_assignment_suggestions"
    __table_args__ = (
        Index("ix_framework_review_assignment_suggestions_org_review", "organization_id", "review_run_id"),
        Index("ix_framework_review_assignment_suggestions_org_status", "organization_id", "status"),
        Index(
            "ix_framework_review_assignment_suggestions_org_review_rank",
            "organization_id",
            "review_run_id",
            "rank",
        ),
    )

    review_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("framework_pack_review_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    suggested_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    score: Mapped[int] = mapped_column(nullable=False, default=0)
    rank: Mapped[int] = mapped_column(nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    scoring_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    generated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    applied_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("framework_pack_review_assignments.id", ondelete="SET NULL"),
        nullable=True,
    )
    dismissed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
