import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class FrameworkContentImport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "framework_content_imports"
    __table_args__ = (
        Index("ix_framework_content_imports_framework", "framework_id"),
        Index("ix_framework_content_imports_org", "organization_id"),
        Index("ix_framework_content_imports_status", "status"),
    )

    organization_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    framework_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("frameworks.id", ondelete="SET NULL"), nullable=True)
    import_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    coverage_level: Mapped[str] = mapped_column(String(32), nullable=False, default="starter")
    imported_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
