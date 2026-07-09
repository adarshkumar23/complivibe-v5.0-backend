import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class VendorGeopoliticalExposure(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    """Records that a given vendor operates in / is exposed to a given region.

    This is a small, feature-owned table -- it does NOT modify ``Vendor`` --
    that lets an org declare "Vendor X operates in region Y" so
    ``GeopoliticalRiskService.get_summary`` can cross-reference active
    ``GeopoliticalRiskSignal`` rows against an org's own vendors.
    """

    __tablename__ = "vendor_geopolitical_exposure"
    __table_args__ = (
        Index("ix_vendor_geo_exposure_org_vendor", "organization_id", "vendor_id"),
        Index("ix_vendor_geo_exposure_org_region", "organization_id", "region"),
    )

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False
    )
    region: Mapped[str] = mapped_column(String(100), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Cascade tracking: set the first time a critical GeopoliticalRiskSignal for this
    # exposure's region creates a Risk register entry for this vendor, so repeat
    # critical signals for the same region don't spam duplicate Risk rows. See
    # GeopoliticalRiskService._cascade_critical_signals_to_vendor_risk.
    cascaded_risk_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("risks.id", ondelete="SET NULL"), nullable=True
    )
    last_cascaded_severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_cascaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
