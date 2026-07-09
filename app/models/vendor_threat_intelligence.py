import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class VendorThreatIntelligence(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "vendor_threat_intelligence"
    __table_args__ = (
        Index("ix_vendor_threat_intel_org_vendor", "organization_id", "vendor_id"),
        Index("ix_vendor_threat_intel_org_computed", "organization_id", "computed_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    vendor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    signals_used: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Nullable for the same reason as VendorExternalRating.composite_score: when zero
    # of the underlying signals returned real data, there is no honest threat score to
    # report. A fabricated 0.0 would read as "confirmed clean" (a false negative), so
    # NULL explicitly means "no data", not "no threat found".
    threat_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    # 0-100: percentage of the scoring weight actually backed by real signal data.
    confidence: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, server_default="0")
    indicators_found: Mapped[dict | list] = mapped_column(JSON, nullable=False, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
