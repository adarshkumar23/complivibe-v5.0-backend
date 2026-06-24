import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AutomationRule(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "automation_rules"
    __table_args__ = (
        Index("ix_automation_rules_org_status", "organization_id", "status"),
        Index("ix_automation_rules_org_trigger", "organization_id", "trigger_type"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(64), nullable=False, default="manual_scan")
    condition_type: Mapped[str] = mapped_column(String(64), nullable=False)
    condition_config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    action_config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    schedule_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    schedule_cadence: Mapped[str | None] = mapped_column(String(32), nullable=True)
    schedule_timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    schedule_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    schedule_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    schedule_window_start: Mapped[str | None] = mapped_column(String(5), nullable=True)
    schedule_window_end: Mapped[str | None] = mapped_column(String(5), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_scheduled_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_dry_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    run_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="live")
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    version_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
