import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AIGovernanceReview(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_governance_reviews"
    __table_args__ = (
        CheckConstraint(
            "review_type IN ('initial_approval', 'periodic', 'triggered', 'pre_deployment')",
            name="ck_ai_governance_reviews_review_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'in_review', 'approved', 'rejected', 'conditional')",
            name="ck_ai_governance_reviews_status",
        ),
        Index("ix_ai_governance_reviews_org_system", "organization_id", "ai_system_id", "status"),
        Index("ix_ai_governance_reviews_org_reviewer_status", "organization_id", "assigned_reviewer_id", "status"),
    )

    ai_system_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=False)
    review_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    assigned_reviewer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    conditions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
