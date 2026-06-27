import uuid
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class AIRiskAssessmentQuestion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ai_risk_assessment_questions"
    __table_args__ = (
        CheckConstraint(
            "risk_dimension IN ('bias', 'fairness', 'explainability', 'privacy', 'misuse', 'security')",
            name="ck_ai_risk_assessment_questions_dimension",
        ),
        Index("ix_ai_risk_assessment_questions_dimension_order", "risk_dimension", "order_index"),
    )

    risk_dimension: Mapped[str] = mapped_column(String(50), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    weight: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False, default=Decimal("1.0"))
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
