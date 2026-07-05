import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin

OT_ICS_FINDING_TYPES = (
    "unpatched_firmware",
    "default_credentials",
    "unauthorized_network_bridge",
    "anomalous_traffic",
    "protocol_violation",
    "other",
)

OT_ICS_FINDING_SEVERITIES = ("low", "medium", "high", "critical")


class OtIcsFinding(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    """A convergence-monitoring finding reported against an OT/ICS asset."""

    __tablename__ = "ot_ics_findings"
    __table_args__ = (
        CheckConstraint(
            "finding_type IN ('unpatched_firmware', 'default_credentials', 'unauthorized_network_bridge', "
            "'anomalous_traffic', 'protocol_violation', 'other')",
            name="ck_ot_ics_findings_finding_type",
        ),
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_ot_ics_findings_severity",
        ),
        Index("ix_ot_ics_findings_org_asset", "organization_id", "asset_id"),
        Index("ix_ot_ics_findings_org_severity", "organization_id", "severity"),
        Index("ix_ot_ics_findings_org_detected_at", "organization_id", "detected_at"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ot_ics_assets.id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("ot_ics_agents.id", ondelete="SET NULL"), nullable=True)
    finding_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
