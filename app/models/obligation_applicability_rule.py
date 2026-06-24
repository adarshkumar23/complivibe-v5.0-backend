import uuid

from sqlalchemy import ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ObligationApplicabilityRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "obligation_applicability_rules"
    __table_args__ = (
        Index("ix_obligation_app_rules_framework", "framework_id"),
        Index("ix_obligation_app_rules_obligation", "obligation_id"),
        Index("ix_obligation_app_rules_question", "question_id"),
        Index("ix_obligation_app_rules_status", "status"),
    )

    framework_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("frameworks.id", ondelete="CASCADE"), nullable=False)
    obligation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("obligations.id", ondelete="CASCADE"), nullable=False)
    question_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("obligation_applicability_questions.id", ondelete="SET NULL"),
        nullable=True,
    )
    rule_key: Mapped[str] = mapped_column(String(128), nullable=False)
    operator: Mapped[str] = mapped_column(String(32), nullable=False)
    expected_value_json: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON, nullable=True)
    result_applicability: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
