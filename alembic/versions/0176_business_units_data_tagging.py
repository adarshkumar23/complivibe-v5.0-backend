"""business units data tagging

Revision ID: 0176_business_units_data_tagging
Revises: 0175_onboarding_flow_apis
Create Date: 2026-06-30 07:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0176_business_units_data_tagging"
down_revision: str | None = "0175_onboarding_flow_apis"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return inspector.has_table(table_name)


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(col.get("name") == column_name for col in inspector.get_columns(table_name))


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(idx.get("name") == index_name for idx in inspector.get_indexes(table_name))


def _has_fk(inspector: sa.Inspector, table_name: str, fk_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(fk.get("name") == fk_name for fk in inspector.get_foreign_keys(table_name))


def _add_bu_column_and_fk(
    bind,
    table_name: str,
    fk_name: str,
    idx_name: str,
) -> None:
    inspector = sa.inspect(bind)
    if _has_table(inspector, table_name) and not _has_column(inspector, table_name, "business_unit_id"):
        op.add_column(
            table_name,
            sa.Column("business_unit_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
        inspector = sa.inspect(bind)

    if _has_table(inspector, table_name) and _has_column(inspector, table_name, "business_unit_id") and not _has_fk(
        inspector, table_name, fk_name
    ):
        op.create_foreign_key(
            fk_name,
            table_name,
            "business_units",
            ["business_unit_id"],
            ["id"],
            ondelete="SET NULL",
        )
        inspector = sa.inspect(bind)

    if _has_table(inspector, table_name) and _has_column(inspector, table_name, "business_unit_id") and not _has_index(
        inspector, table_name, idx_name
    ):
        op.create_index(
            idx_name,
            table_name,
            ["business_unit_id"],
            unique=False,
            postgresql_where=sa.text("business_unit_id IS NOT NULL"),
            sqlite_where=sa.text("business_unit_id IS NOT NULL"),
        )


def _drop_bu_column_and_fk(
    bind,
    table_name: str,
    fk_name: str,
    idx_name: str,
) -> None:
    inspector = sa.inspect(bind)
    if _has_table(inspector, table_name) and _has_index(inspector, table_name, idx_name):
        op.drop_index(idx_name, table_name=table_name)
        inspector = sa.inspect(bind)

    if _has_table(inspector, table_name) and _has_fk(inspector, table_name, fk_name):
        op.drop_constraint(fk_name, table_name, type_="foreignkey")
        inspector = sa.inspect(bind)

    if _has_table(inspector, table_name) and _has_column(inspector, table_name, "business_unit_id"):
        op.drop_column(table_name, "business_unit_id")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "business_units"):
        op.create_table(
            "business_units",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
            sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("name", sa.VARCHAR(length=150), nullable=False),
            sa.Column("code", sa.VARCHAR(length=30), nullable=False),
            sa.Column("parent_bu_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("cost_center", sa.VARCHAR(length=50), nullable=True),
            sa.Column("bu_lead_user_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_bu_org_id", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["parent_bu_id"], ["business_units.id"], name="fk_bu_parent_id", ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["bu_lead_user_id"], ["users.id"], name="fk_bu_lead_user", ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_bu_created_by", ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
        )

    inspector = sa.inspect(bind)
    if _has_table(inspector, "business_units") and not _has_index(inspector, "business_units", "ux_bu_org_code_active"):
        op.create_index(
            "ux_bu_org_code_active",
            "business_units",
            ["organization_id", "code"],
            unique=True,
            postgresql_where=sa.text("deleted_at IS NULL"),
            sqlite_where=sa.text("deleted_at IS NULL"),
        )
    inspector = sa.inspect(bind)
    if _has_table(inspector, "business_units") and not _has_index(inspector, "business_units", "ix_bu_org_active"):
        op.create_index("ix_bu_org_active", "business_units", ["organization_id", "is_active"], unique=False)
    inspector = sa.inspect(bind)
    if _has_table(inspector, "business_units") and not _has_index(inspector, "business_units", "ix_bu_parent"):
        op.create_index("ix_bu_parent", "business_units", ["parent_bu_id"], unique=False)

    _add_bu_column_and_fk(bind, "risks", "fk_risks_bu_id", "ix_risks_bu_id")
    _add_bu_column_and_fk(bind, "controls", "fk_controls_bu_id", "ix_controls_bu_id")
    _add_bu_column_and_fk(bind, "compliance_policies", "fk_comp_pols_bu_id", "ix_comp_pols_bu_id")
    _add_bu_column_and_fk(bind, "vendors", "fk_vendors_bu_id", "ix_vendors_bu_id")
    _add_bu_column_and_fk(bind, "ai_systems", "fk_ai_systems_bu_id", "ix_ai_systems_bu_id")


def downgrade() -> None:
    bind = op.get_bind()

    _drop_bu_column_and_fk(bind, "ai_systems", "fk_ai_systems_bu_id", "ix_ai_systems_bu_id")
    _drop_bu_column_and_fk(bind, "vendors", "fk_vendors_bu_id", "ix_vendors_bu_id")
    _drop_bu_column_and_fk(bind, "compliance_policies", "fk_comp_pols_bu_id", "ix_comp_pols_bu_id")
    _drop_bu_column_and_fk(bind, "controls", "fk_controls_bu_id", "ix_controls_bu_id")
    _drop_bu_column_and_fk(bind, "risks", "fk_risks_bu_id", "ix_risks_bu_id")

    inspector = sa.inspect(bind)
    if _has_table(inspector, "business_units") and _has_index(inspector, "business_units", "ix_bu_parent"):
        op.drop_index("ix_bu_parent", table_name="business_units")
    inspector = sa.inspect(bind)
    if _has_table(inspector, "business_units") and _has_index(inspector, "business_units", "ix_bu_org_active"):
        op.drop_index("ix_bu_org_active", table_name="business_units")
    inspector = sa.inspect(bind)
    if _has_table(inspector, "business_units") and _has_index(inspector, "business_units", "ux_bu_org_code_active"):
        op.drop_index("ux_bu_org_code_active", table_name="business_units")
    inspector = sa.inspect(bind)
    if _has_table(inspector, "business_units"):
        op.drop_table("business_units")
