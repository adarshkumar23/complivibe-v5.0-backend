import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class OtIcsSegmentRiskDetection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tracks per-org/network_segment OT/ICS finding concentration.

    Mirrors ``VendorConcentrationRiskDetection``'s create-once/keep-risk_id pattern:
    once a network segment's open high-or-critical finding count crosses
    ``threshold_count``, a single Risk register entry is created for that segment
    and its id is kept here so repeated findings on an already-flagged segment don't
    spam duplicate Risk rows.
    """

    __tablename__ = "ot_ics_segment_risk_detections"
    __table_args__ = (
        UniqueConstraint("organization_id", "network_segment", name="uq_ot_ics_segment_risk_org_segment"),
        Index("ix_ot_ics_segment_risk_org_segment", "organization_id", "network_segment"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    network_segment: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="below_threshold")
    open_high_or_critical_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    threshold_count: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    risk_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("risks.id", ondelete="SET NULL"), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
