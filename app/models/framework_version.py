import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class FrameworkVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "framework_versions"
    __table_args__ = (
        Index("ix_framework_versions_framework_status", "framework_id", "status"),
        Index("ix_framework_versions_framework_coverage", "framework_id", "coverage_level"),
    )

    framework_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("frameworks.id", ondelete="CASCADE"), nullable=False)
    version_label: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    coverage_level: Mapped[str] = mapped_column(String(32), nullable=False, default="metadata_only")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
