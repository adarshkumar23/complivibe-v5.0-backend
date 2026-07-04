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
    composite_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
