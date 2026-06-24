import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class VendorAssessmentQuestion(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "vendor_assessment_questions"
    __table_args__ = (
        Index("ix_vendor_assessment_questions_org_assessment", "organization_id", "assessment_id"),
        Index("ix_vendor_assessment_questions_org_category", "organization_id", "question_category"),
        Index("ix_vendor_assessment_questions_org_response", "organization_id", "response_status"),
        Index("ix_vendor_assessment_questions_org_sort", "organization_id", "assessment_id", "sort_order"),
    )

    assessment_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("vendor_assessments.id", ondelete="CASCADE"), nullable=False)
    question_text: Mapped[str] = mapped_column(String(500), nullable=False)
    question_category: Mapped[str] = mapped_column(String(32), nullable=False)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_answered")

    answered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sort_order: Mapped[int] = mapped_column(nullable=False, default=0)
