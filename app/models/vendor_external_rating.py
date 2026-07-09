import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class VendorExternalRating(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "vendor_external_ratings"
    __table_args__ = (
        Index("ix_vendor_external_ratings_org_vendor", "organization_id", "vendor_id"),
        Index("ix_vendor_external_ratings_org_computed", "organization_id", "computed_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    vendor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    signals_used: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Nullable: when zero of the 4 underlying signals returned real data (all
    # skipped/errored), there is no honest composite score to report -- storing a
    # fabricated 0.0 would misrepresent "no data" as "confirmed terrible security
    # posture". NULL means exactly that: no score could be computed this run.
    composite_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    # 0-100: percentage of the scoring weight actually backed by real signal data
    # (rather than skipped-for-no-api-key or errored/rate-limited). Lets a reviewer
    # tell a confident bad reading apart from a thin/empty one instead of both
    # looking identical.
    confidence: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, server_default="0")
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
