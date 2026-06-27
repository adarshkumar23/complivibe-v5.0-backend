import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class DataIncident(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "data_incidents"
    __table_args__ = (
        CheckConstraint(
            "detector_type IN ('anomaly_rule', 'quality_breach', 'retention_violation', 'residency_violation', 'manual')",
            name="ck_data_incidents_detector_type",
        ),
        CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low')",
            name="ck_data_incidents_severity",
        ),
        CheckConstraint(
            "status IN ('new', 'investigating', 'contained', 'resolved', 'dismissed')",
            name="ck_data_incidents_status",
        ),
        CheckConstraint(
            "detected_by IN ('scheduler', 'rule_engine', 'manual', 'api')",
            name="ck_data_incidents_detected_by",
        ),
        Index("ix_data_incidents_org_asset_status", "organization_id", "data_asset_id", "status"),
        Index("ix_data_incidents_org_severity_status", "organization_id", "severity", "status"),
        Index("ix_data_incidents_org_detector", "organization_id", "detector_type"),
        Index("ix_data_incidents_detected_at", "detected_at"),
    )

    data_asset_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("data_assets.id", ondelete="CASCADE"), nullable=False)
    detector_type: Mapped[str] = mapped_column(String(50), nullable=False)
    detector_ref_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new")
    rule_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    evidence_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    linked_issue_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    detected_by: Mapped[str] = mapped_column(String(20), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
