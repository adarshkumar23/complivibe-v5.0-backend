import uuid

from sqlalchemy import ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ObligationControlSuggestion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "obligation_control_suggestions"
    __table_args__ = (
        Index("ix_obligation_control_suggestions_framework", "framework_id"),
        Index("ix_obligation_control_suggestions_obligation", "obligation_id"),
    )

    framework_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("frameworks.id", ondelete="CASCADE"), nullable=False)
    obligation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("obligations.id", ondelete="CASCADE"), nullable=False)
    control_title: Mapped[str] = mapped_column(String(255), nullable=False)
    control_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    control_domain: Mapped[str | None] = mapped_column(String(128), nullable=True)
    control_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
