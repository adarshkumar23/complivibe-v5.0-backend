import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class QuestionnaireTemplateQuestion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "questionnaire_template_questions"
    __table_args__ = (
        CheckConstraint(
            "question_type IN ('yes_no', 'multiple_choice', 'text', 'numeric')",
            name="ck_questionnaire_template_questions_question_type",
        ),
        Index(
            "ix_questionnaire_template_questions_template_section_order",
            "template_id",
            "section_id",
            "order_index",
        ),
        Index("ix_questionnaire_template_questions_category_tag", "category_tag"),
        Index("ix_questionnaire_template_questions_framework_ref", "framework_ref"),
    )

    template_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("questionnaire_templates.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("questionnaire_template_sections.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str] = mapped_column(String(50), nullable=False)
    category_tag: Mapped[str] = mapped_column(String(100), nullable=False)
    framework_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    allowed_values: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    expected_answer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    order_index: Mapped[int] = mapped_column(nullable=False, default=0)
    help_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
