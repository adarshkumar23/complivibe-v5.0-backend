import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class SchedulerRunLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "scheduler_run_logs"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'completed', 'failed')", name="ck_scheduler_run_logs_status"),
        Index("ix_scheduler_run_logs_job_started", "job_name", "started_at"),
        Index("ix_scheduler_run_logs_status_started", "status", "started_at"),
        Index("ix_scheduler_run_logs_started", "started_at"),
    )

    job_name: Mapped[str] = mapped_column(String(100), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    records_processed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

