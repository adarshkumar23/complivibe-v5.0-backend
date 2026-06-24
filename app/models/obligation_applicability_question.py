import uuid

from sqlalchemy import Boolean, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ObligationApplicabilityQuestion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "obligation_applicability_questions"
    __table_args__ = (
        Index("ix_obligation_questions_framework", "framework_id"),
        Index("ix_obligation_questions_obligation", "obligation_id"),
        Index("ix_obligation_questions_org", "organization_id"),
        Index("ix_obligation_questions_key", "framework_id", "question_key"),
    )

    organization_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    framework_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("frameworks.id", ondelete="CASCADE"), nullable=False)
    obligation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("obligations.id", ondelete="CASCADE"), nullable=True)
    question_key: Mapped[str] = mapped_column(String(128), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    help_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_type: Mapped[str] = mapped_column(String(32), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
