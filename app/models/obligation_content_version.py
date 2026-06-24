import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class ObligationContentVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "obligation_content_versions"
    __table_args__ = (
        Index("ix_obligation_content_versions_obligation", "obligation_id"),
        Index("ix_obligation_content_versions_review", "review_status"),
    )

    obligation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("obligations.id", ondelete="CASCADE"), nullable=False)
    version_label: Mapped[str] = mapped_column(String(64), nullable=False)
    obligation_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    coverage_level: Mapped[str] = mapped_column(String(32), nullable=False, default="starter")
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unreviewed")
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("obligation_content_versions.id", ondelete="SET NULL"), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
