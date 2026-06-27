import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class InboundQuestionnaireItem(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "inbound_questionnaire_items"
    __table_args__ = (
        CheckConstraint(
            "question_type IN ('yes_no', 'text', 'multiple_choice', 'numeric')",
            name="ck_inbound_questionnaire_items_question_type",
        ),
        CheckConstraint(
            "source_type IN ('evidence', 'control', 'certification', 'policy', 'previous_answer') OR source_type IS NULL",
            name="ck_inbound_questionnaire_items_source_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'drafted', 'needs_review', 'approved', 'rejected', 'sent')",
            name="ck_inbound_questionnaire_items_status",
        ),
        Index("ix_inbound_questionnaire_items_session_id", "session_id"),
        Index("ix_inbound_questionnaire_items_org_status", "organization_id", "status"),
        Index("ix_inbound_questionnaire_items_category_tag", "category_tag"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("inbound_questionnaire_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str] = mapped_column(String(50), nullable=False, default="text")
    category_tag: Mapped[str | None] = mapped_column(String(100), nullable=True)
    framework_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    order_index: Mapped[int] = mapped_column(nullable=False, default=0)

    suggested_answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    source_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    confidence_score: Mapped[int | None] = mapped_column(nullable=True)
    confidence_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    final_answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
