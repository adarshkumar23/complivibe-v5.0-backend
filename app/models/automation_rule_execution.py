import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AutomationRuleExecution(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "automation_rule_executions"
    __table_args__ = (
        Index("ix_automation_exec_org_rule", "organization_id", "rule_id"),
        Index("ix_automation_exec_org_status", "organization_id", "status"),
    )

    rule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("automation_rules.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    matched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    action_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trigger_source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual_rule_run")
    dry_run: Mapped[bool] = mapped_column(nullable=False, default=False)
    rule_version: Mapped[int | None] = mapped_column(nullable=True)
    scheduled_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_scope: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
