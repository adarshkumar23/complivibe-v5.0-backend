import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, JSON, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class VendorCriticalitySetting(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "vendor_criticality_settings"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_vendor_criticality_settings_org"),
        Index("ix_vendor_criticality_settings_org", "organization_id"),
    )

    revenue_dependency_weight: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.2500"))
    data_volume_weight: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.2500"))
    operational_criticality_weight: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.2500"))
    substitutability_weight: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.2500"))
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class VendorCriticalityProfile(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "vendor_criticality_profiles"
    __table_args__ = (
        UniqueConstraint("organization_id", "vendor_id", name="uq_vendor_criticality_profiles_org_vendor"),
        Index("ix_vendor_criticality_profiles_org_vendor", "organization_id", "vendor_id"),
        Index("ix_vendor_criticality_profiles_org_tier", "organization_id", "criticality_tier"),
        Index("ix_vendor_criticality_profiles_org_score", "organization_id", "criticality_score"),
    )

    vendor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    revenue_dependency_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    data_volume_tier: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    operational_criticality: Mapped[str] = mapped_column(String(32), nullable=False, default="low")
    substitutability_score: Mapped[int] = mapped_column(nullable=False, default=1)
    criticality_score: Mapped[int] = mapped_column(nullable=False, default=0)
    criticality_tier: Mapped[str] = mapped_column(String(32), nullable=False, default="low")
    score_explanation_json: Mapped[dict | list] = mapped_column(JSON, nullable=False, default=dict)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
