import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class QuestionnaireScoringRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "questionnaire_scoring_rules"
    __table_args__ = (
        CheckConstraint(
            "condition_operator IN ('eq', 'ne', 'contains', 'not_contains', 'gte', 'lte')",
            name="ck_questionnaire_scoring_rules_condition_operator",
        ),
        UniqueConstraint(
            "organization_id",
            "question_id",
            "condition_operator",
            "condition_value",
            name="uq_questionnaire_scoring_rules_org_question_condition",
        ),
        Index("ix_questionnaire_scoring_rules_template_question", "template_id", "question_id"),
        Index("ix_questionnaire_scoring_rules_org_template", "organization_id", "template_id"),
    )

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("questionnaire_templates.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("questionnaire_template_questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    condition_operator: Mapped[str] = mapped_column(String(20), nullable=False)
    condition_value: Mapped[str] = mapped_column(String(255), nullable=False)
    score_delta: Mapped[int] = mapped_column(nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
