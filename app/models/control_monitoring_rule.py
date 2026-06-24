import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ControlMonitoringRule(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "control_monitoring_rules"
    __table_args__ = (
        Index("ix_control_monitoring_rules_org_status", "organization_id", "status"),
        Index("ix_control_monitoring_rules_org_type", "organization_id", "rule_type"),
        Index("ix_control_monitoring_rules_org_created", "organization_id", "created_at"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    rule_type: Mapped[str] = mapped_column(String(64), nullable=False)
    condition_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    action_config_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    scope_definition_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    archive_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
