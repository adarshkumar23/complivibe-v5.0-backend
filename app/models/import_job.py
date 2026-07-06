import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class ImportJob(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "import_jobs"
    __table_args__ = (
        CheckConstraint(
            "source_tool IN ('vanta', 'drata', 'sprinto', 'scrut', 'generic')",
            name="ck_import_jobs_source_tool",
        ),
        CheckConstraint(
            "status IN ('queued', 'processing', 'preview_ready', 'completed', 'failed')",
            name="ck_import_jobs_status",
        ),
        CheckConstraint(
            "conflict_strategy IN ('skip', 'update')",
            name="ck_import_jobs_conflict_strategy",
        ),
        CheckConstraint("progress_current >= 0", name="ck_import_jobs_progress_current"),
        CheckConstraint("progress_total >= 0", name="ck_import_jobs_progress_total"),
        Index("ix_import_jobs_org_status", "organization_id", "status"),
        Index("ix_import_jobs_org_source", "organization_id", "source_tool"),
        Index("ix_import_jobs_created_at", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_tool: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    progress_current: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    conflict_strategy: Mapped[str] = mapped_column(String(16), nullable=False, default="skip")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
