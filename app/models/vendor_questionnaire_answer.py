import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class VendorQuestionnaireAnswer(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "vendor_questionnaire_answers"
    __table_args__ = (
        UniqueConstraint("response_id", "question_id", name="uq_vendor_questionnaire_answers_response_question"),
        Index("ix_vendor_questionnaire_answers_response_id", "response_id"),
        Index("ix_vendor_questionnaire_answers_org_response", "organization_id", "response_id"),
    )

    response_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("vendor_questionnaire_responses.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("questionnaire_template_questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    score_contribution: Mapped[int | None] = mapped_column(nullable=True)
    is_answered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
