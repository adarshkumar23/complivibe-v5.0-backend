import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin

OT_ICS_ASSET_TYPES = (
    "plc",
    "scada",
    "hmi",
    "rtu",
    "historian",
    "ics_gateway",
    "sensor",
    "actuator",
    "other",
)

OT_ICS_CRITICALITY_LEVELS = ("low", "medium", "high", "critical")

OT_ICS_ASSET_STATUSES = ("active", "decommissioned", "under_maintenance")


class OtIcsAsset(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    """OT/ICS convergence asset inventory (PLCs, SCADA, HMIs, RTUs, historians, etc)."""

    __tablename__ = "ot_ics_assets"
    __table_args__ = (
        CheckConstraint(
            "asset_type IN ('plc', 'scada', 'hmi', 'rtu', 'historian', 'ics_gateway', 'sensor', 'actuator', 'other')",
            name="ck_ot_ics_assets_asset_type",
        ),
        CheckConstraint(
            "criticality IN ('low', 'medium', 'high', 'critical')",
            name="ck_ot_ics_assets_criticality",
        ),
        CheckConstraint(
            "status IN ('active', 'decommissioned', 'under_maintenance')",
            name="ck_ot_ics_assets_status",
        ),
        Index("ix_ot_ics_assets_org_asset_type", "organization_id", "asset_type"),
        Index("ix_ot_ics_assets_org_criticality", "organization_id", "criticality"),
        Index("ix_ot_ics_assets_org_network_segment", "organization_id", "network_segment"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(50), nullable=False)
    network_segment: Mapped[str | None] = mapped_column(String(100), nullable=True)
    criticality: Mapped[str] = mapped_column(String(20), nullable=False)
    linked_data_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("data_assets.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
