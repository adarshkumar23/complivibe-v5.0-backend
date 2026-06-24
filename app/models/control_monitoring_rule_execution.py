import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class ControlMonitoringRuleExecution(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "control_monitoring_rule_executions"
    __table_args__ = (
        Index("ix_control_monitoring_rule_executions_org_rule", "organization_id", "rule_id"),
        Index("ix_control_monitoring_rule_executions_org_triggered", "organization_id", "triggered_at"),
        Index("ix_control_monitoring_rule_executions_org_dry_run", "organization_id", "dry_run"),
    )

    rule_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("control_monitoring_rules.id", ondelete="CASCADE"), nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    matched_count: Mapped[int] = mapped_column(nullable=False, default=0)
    action_count: Mapped[int] = mapped_column(nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(nullable=False, default=0)
    execution_summary_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
