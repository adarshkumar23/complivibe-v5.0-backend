import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class VendorConcentrationRiskDetection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "vendor_concentration_risk_detections"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_vendor_concentration_risk_detection_org"),
        Index("ix_vendor_concentration_risk_org_status", "organization_id", "status"),
        Index("ix_vendor_concentration_risk_org_risk", "organization_id", "risk_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="below_threshold")
    hhi_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    threshold_hhi_score: Mapped[int] = mapped_column(Integer, nullable=False, default=1800)
    top_vendor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True)
    top_vendor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    top_vendor_share_basis_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    exposure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    critical_vendor_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dependency_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    risk_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("risks.id", ondelete="SET NULL"), nullable=True)
    convention_source_title: Mapped[str] = mapped_column(String(255), nullable=False)
    convention_source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    criticality_source_title: Mapped[str] = mapped_column(String(255), nullable=False)
    criticality_source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    evidence_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recomputed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    recomputed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
