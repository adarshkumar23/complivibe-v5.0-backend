import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, JSON, Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class CarbonEmissionsReading(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "carbon_emissions_readings"
    __table_args__ = (
        CheckConstraint("scope IN ('scope1', 'scope2', 'scope3')", name="ck_carbon_emissions_readings_scope"),
        CheckConstraint("value >= 0", name="ck_carbon_emissions_readings_value_nonnegative"),
        Index("ix_carbon_readings_org_scope_period", "organization_id", "scope", "period_start", "period_end"),
        Index("ix_carbon_readings_org_business_unit", "organization_id", "business_unit_id"),
        Index("ix_carbon_readings_org_source", "organization_id", "source"),
    )

    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    business_unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("business_units.id", ondelete="SET NULL"), nullable=True)
    source_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
