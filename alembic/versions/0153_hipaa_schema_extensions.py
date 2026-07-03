"""hipaa schema extensions

Revision ID: 0153_hipaa_schema_extensions
Revises: 0152_nist_800_53_seed
Create Date: 2026-06-27 16:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0153_hipaa_schema_extensions"
down_revision: str | None = "0152_nist_800_53_seed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _has_constraint(inspector: sa.Inspector, table_name: str, constraint_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(item.get("name") == constraint_name for item in inspector.get_check_constraints(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_column(inspector, "dpa_agreements", "is_baa") is False:
        op.add_column("dpa_agreements", sa.Column("is_baa", sa.Boolean(), nullable=False, server_default=sa.false()))
    if _has_column(inspector, "dpa_agreements", "baa_effective_date") is False:
        op.add_column("dpa_agreements", sa.Column("baa_effective_date", sa.Date(), nullable=True))
    if _has_column(inspector, "dpa_agreements", "baa_includes_phi") is False:
        op.add_column("dpa_agreements", sa.Column("baa_includes_phi", sa.Boolean(), nullable=False, server_default=sa.false()))
    if _has_column(inspector, "dpa_agreements", "baa_subcontractor_clause") is False:
        op.add_column("dpa_agreements", sa.Column("baa_subcontractor_clause", sa.Boolean(), nullable=False, server_default=sa.false()))
    if _has_column(inspector, "dpa_agreements", "baa_breach_notification_days") is False:
        op.add_column(
            "dpa_agreements",
            sa.Column("baa_breach_notification_days", sa.Integer(), nullable=False, server_default=sa.text("60")),
        )
    if _has_column(inspector, "dpa_agreements", "hipaa_covered_entity_type") is False:
        op.add_column("dpa_agreements", sa.Column("hipaa_covered_entity_type", sa.VARCHAR(length=30), nullable=True))

    inspector = sa.inspect(bind)
    if _has_constraint(inspector, "dpa_agreements", "ck_dpa_agreements_hipaa_covered_entity_type"):
        op.drop_constraint("ck_dpa_agreements_hipaa_covered_entity_type", "dpa_agreements", type_="check")
    op.create_check_constraint(
        "ck_dpa_agreements_hipaa_covered_entity_type",
        "dpa_agreements",
        "hipaa_covered_entity_type IS NULL OR hipaa_covered_entity_type IN ('covered_entity', 'business_associate', 'subcontractor')",
    )

    inspector = sa.inspect(bind)
    if _has_column(inspector, "data_assets", "is_phi") is False:
        op.add_column("data_assets", sa.Column("is_phi", sa.Boolean(), nullable=False, server_default=sa.false()))
    if _has_column(inspector, "data_assets", "hipaa_safeguard_required") is False:
        op.add_column("data_assets", sa.Column("hipaa_safeguard_required", sa.VARCHAR(length=20), nullable=True))

    inspector = sa.inspect(bind)
    if _has_constraint(inspector, "data_assets", "ck_data_assets_hipaa_safeguard_required"):
        op.drop_constraint("ck_data_assets_hipaa_safeguard_required", "data_assets", type_="check")
    op.create_check_constraint(
        "ck_data_assets_hipaa_safeguard_required",
        "data_assets",
        "hipaa_safeguard_required IS NULL OR hipaa_safeguard_required IN ('administrative', 'physical', 'technical', 'all')",
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_constraint(inspector, "data_assets", "ck_data_assets_hipaa_safeguard_required"):
        op.drop_constraint("ck_data_assets_hipaa_safeguard_required", "data_assets", type_="check")

    inspector = sa.inspect(bind)
    if _has_column(inspector, "data_assets", "hipaa_safeguard_required"):
        op.drop_column("data_assets", "hipaa_safeguard_required")
    if _has_column(inspector, "data_assets", "is_phi"):
        op.drop_column("data_assets", "is_phi")

    inspector = sa.inspect(bind)
    if _has_constraint(inspector, "dpa_agreements", "ck_dpa_agreements_hipaa_covered_entity_type"):
        op.drop_constraint("ck_dpa_agreements_hipaa_covered_entity_type", "dpa_agreements", type_="check")

    inspector = sa.inspect(bind)
    if _has_column(inspector, "dpa_agreements", "hipaa_covered_entity_type"):
        op.drop_column("dpa_agreements", "hipaa_covered_entity_type")
    if _has_column(inspector, "dpa_agreements", "baa_breach_notification_days"):
        op.drop_column("dpa_agreements", "baa_breach_notification_days")
    if _has_column(inspector, "dpa_agreements", "baa_subcontractor_clause"):
        op.drop_column("dpa_agreements", "baa_subcontractor_clause")
    if _has_column(inspector, "dpa_agreements", "baa_includes_phi"):
        op.drop_column("dpa_agreements", "baa_includes_phi")
    if _has_column(inspector, "dpa_agreements", "baa_effective_date"):
        op.drop_column("dpa_agreements", "baa_effective_date")
    if _has_column(inspector, "dpa_agreements", "is_baa"):
        op.drop_column("dpa_agreements", "is_baa")
