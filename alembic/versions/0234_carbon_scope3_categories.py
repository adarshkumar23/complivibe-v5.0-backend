"""add scope3_category, emission_factor sourcing, and corrected_at to carbon_emissions_readings

Revision ID: 0234_carbon_scope3
Revises: 0233_connector_status
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0234_carbon_scope3"
down_revision: str | None = "0233_connector_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

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
    "unspecified_legacy",
)
_SCOPE3_CATEGORY_SQL_LIST = ", ".join(f"'{c}'" for c in SCOPE3_CATEGORIES)


def upgrade() -> None:
    op.add_column("carbon_emissions_readings", sa.Column("scope3_category", sa.String(length=60), nullable=True))
    op.add_column("carbon_emissions_readings", sa.Column("emission_factor_source", sa.String(length=120), nullable=True))
    op.add_column("carbon_emissions_readings", sa.Column("emission_factor_version", sa.String(length=40), nullable=True))
    op.add_column("carbon_emissions_readings", sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=True))

    # Backfill any pre-existing scope3 rows into the legacy bucket so the new NOT NULL-by-scope
    # check constraint below does not break on historical data.
    op.execute(
        "UPDATE carbon_emissions_readings SET scope3_category = 'unspecified_legacy' "
        "WHERE scope = 'scope3' AND scope3_category IS NULL"
    )

    op.create_check_constraint(
        "ck_carbon_emissions_readings_scope3_category",
        "carbon_emissions_readings",
        f"scope3_category IS NULL OR scope3_category IN ({_SCOPE3_CATEGORY_SQL_LIST})",
    )
    op.create_check_constraint(
        "ck_carbon_emissions_readings_scope3_category_required",
        "carbon_emissions_readings",
        "(scope = 'scope3' AND scope3_category IS NOT NULL) OR (scope != 'scope3' AND scope3_category IS NULL)",
    )
    op.create_index(
        "ix_carbon_readings_org_source_record",
        "carbon_emissions_readings",
        ["organization_id", "source", "source_record_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_carbon_readings_org_source_record", table_name="carbon_emissions_readings")
    op.drop_constraint("ck_carbon_emissions_readings_scope3_category_required", "carbon_emissions_readings", type_="check")
    op.drop_constraint("ck_carbon_emissions_readings_scope3_category", "carbon_emissions_readings", type_="check")
    op.drop_column("carbon_emissions_readings", "corrected_at")
    op.drop_column("carbon_emissions_readings", "emission_factor_version")
    op.drop_column("carbon_emissions_readings", "emission_factor_source")
    op.drop_column("carbon_emissions_readings", "scope3_category")
