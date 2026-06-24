import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ControlMonitoringAlert(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "control_monitoring_alerts"
    __table_args__ = (
        Index("ix_control_monitoring_alerts_org_status", "organization_id", "status"),
        Index("ix_control_monitoring_alerts_org_severity", "organization_id", "severity"),
        Index("ix_control_monitoring_alerts_org_type", "organization_id", "alert_type"),
        Index("ix_control_monitoring_alerts_org_assigned", "organization_id", "assigned_to_user_id"),
        Index("ix_control_monitoring_alerts_org_rule", "organization_id", "rule_id"),
        Index("ix_control_monitoring_alerts_org_definition", "organization_id", "definition_id"),
        Index("ix_control_monitoring_alerts_org_control", "organization_id", "control_id"),
    )

    rule_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("control_monitoring_rules.id", ondelete="SET NULL"), nullable=True)
    definition_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("control_monitoring_definitions.id", ondelete="SET NULL"), nullable=True)
    control_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("controls.id", ondelete="SET NULL"), nullable=True)

    alert_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    alert_context_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    dismissal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
