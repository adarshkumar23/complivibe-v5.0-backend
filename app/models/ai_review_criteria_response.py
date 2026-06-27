import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AIReviewCriteriaResponse(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_review_criteria_responses"
    __table_args__ = (
        CheckConstraint(
            "response IS NULL OR response IN ('yes', 'no', 'partial', 'na')",
            name="ck_ai_review_criteria_responses_response",
        ),
        UniqueConstraint("review_id", "criterion_key", name="uq_ai_review_criteria_review_key"),
        Index("ix_ai_review_criteria_review", "review_id"),
    )

    review_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ai_governance_reviews.id", ondelete="CASCADE"), nullable=False)
    criterion_key: Mapped[str] = mapped_column(String(100), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str | None] = mapped_column(String(20), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
