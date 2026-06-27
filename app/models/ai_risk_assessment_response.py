import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AIRiskAssessmentResponse(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_risk_assessment_responses"
    __table_args__ = (
        CheckConstraint(
            "response IS NULL OR response IN ('low_risk', 'medium_risk', 'high_risk', 'critical_risk')",
            name="ck_ai_risk_assessment_responses_response",
        ),
        UniqueConstraint("assessment_id", "question_id", name="uq_ai_risk_assessment_response_question"),
        Index("ix_ai_risk_assessment_responses_assessment", "assessment_id"),
        Index("ix_ai_risk_assessment_responses_org_assessment", "organization_id", "assessment_id"),
    )

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_risk_assessments.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_risk_assessment_questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    response: Mapped[str | None] = mapped_column(String(20), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_contribution: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
