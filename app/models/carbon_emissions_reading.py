import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, JSON, Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin

# The 15 categories of the GHG Protocol Corporate Value Chain (Scope 3) Standard.
# Scope 3 is the largest and most commonly under-modeled category (typically 70-95% of a
# company's footprint per CDP) -- readings tagged scope3 MUST be attributed to one of these
# categories rather than reported as a single undifferentiated lump sum.
SCOPE3_CATEGORIES = (
    "purchased_goods_and_services",
    "capital_goods",
    "fuel_and_energy_related_activities",
    "upstream_transportation_and_distribution",
    "waste_generated_in_operations",
    "business_travel",
    "employee_commuting",
    "upstream_leased_assets",
    "downstream_transportation_and_distribution",
    "processing_of_sold_products",
    "use_of_sold_products",
    "end_of_life_treatment_of_sold_products",
    "downstream_leased_assets",
    "franchises",
    "investments",
    # Legacy bucket for rows ingested before category attribution was required; new writes
    # must not use this value (enforced in CarbonAccountingService, not just the DB check).
    "unspecified_legacy",
)

_SCOPE3_CATEGORY_SQL_LIST = ", ".join(f"'{c}'" for c in SCOPE3_CATEGORIES)


class CarbonEmissionsReading(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "carbon_emissions_readings"
    __table_args__ = (
        CheckConstraint("scope IN ('scope1', 'scope2', 'scope3')", name="ck_carbon_emissions_readings_scope"),
        CheckConstraint("value >= 0", name="ck_carbon_emissions_readings_value_nonnegative"),
        CheckConstraint(
            f"scope3_category IS NULL OR scope3_category IN ({_SCOPE3_CATEGORY_SQL_LIST})",
            name="ck_carbon_emissions_readings_scope3_category",
        ),
        CheckConstraint(
            "(scope = 'scope3' AND scope3_category IS NOT NULL) OR (scope != 'scope3' AND scope3_category IS NULL)",
            name="ck_carbon_emissions_readings_scope3_category_required",
        ),
        Index("ix_carbon_readings_org_scope_period", "organization_id", "scope", "period_start", "period_end"),
        Index("ix_carbon_readings_org_business_unit", "organization_id", "business_unit_id"),
        Index("ix_carbon_readings_org_source", "organization_id", "source"),
        Index(
            "ix_carbon_readings_org_source_record",
            "organization_id",
            "source",
            "source_record_id",
            unique=False,
        ),
    )

    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    scope3_category: Mapped[str | None] = mapped_column(String(60), nullable=True)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    business_unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("business_units.id", ondelete="SET NULL"), nullable=True)
    source_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    emission_factor_source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    emission_factor_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    corrected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
