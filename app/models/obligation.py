import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Obligation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "obligations"
    __table_args__ = (
        Index("ix_obligations_framework_status", "framework_id", "status"),
        Index("ix_obligations_jurisdiction", "jurisdiction"),
        Index("ix_obligations_reference_code", "reference_code"),
    )

    framework_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("frameworks.id", ondelete="CASCADE"), nullable=False, index=True)
    framework_section_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("framework_sections.id", ondelete="SET NULL"),
        nullable=True,
    )
    reference_code: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    plain_language_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    obligation_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    jurisdiction: Mapped[str] = mapped_column(String(128), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    parent_obligation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("obligations.id", ondelete="SET NULL"),
        nullable=True,
    )
