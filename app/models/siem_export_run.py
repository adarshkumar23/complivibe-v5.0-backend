import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class SiemExportRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "siem_export_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'failed', 'partial')",
            name="ck_siem_export_runs_status",
        ),
        Index("ix_siem_export_runs_org_config", "organization_id", "config_id"),
        Index("ix_siem_export_runs_started_at", "started_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    config_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("siem_export_configs.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    records_exported: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    cursor_start: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    cursor_end: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
