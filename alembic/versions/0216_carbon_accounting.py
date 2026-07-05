"""add carbon accounting readings

Revision ID: 0216_carbon_accounting
Revises: 0215_xbrl_export_permission
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0216_carbon_accounting"
down_revision: str | None = "0215_xbrl_export_permission"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION_KEY = "carbon_accounting:read"
PERMISSION_DESCRIPTION = "Read carbon accounting dashboards and summaries"


def upgrade() -> None:
    op.create_table(
        "carbon_emissions_readings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("value", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("business_unit_id", sa.Uuid(), nullable=True),
        sa.Column("source_record_id", sa.String(length=255), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("scope IN ('scope1', 'scope2', 'scope3')", name="ck_carbon_emissions_readings_scope"),
        sa.CheckConstraint("value >= 0", name="ck_carbon_emissions_readings_value_nonnegative"),
        sa.ForeignKeyConstraint(["business_unit_id"], ["business_units.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_carbon_emissions_readings_organization_id", "carbon_emissions_readings", ["organization_id"], unique=False)
    op.create_index("ix_carbon_readings_org_scope_period", "carbon_emissions_readings", ["organization_id", "scope", "period_start", "period_end"], unique=False)
    op.create_index("ix_carbon_readings_org_business_unit", "carbon_emissions_readings", ["organization_id", "business_unit_id"], unique=False)
    op.create_index("ix_carbon_readings_org_source", "carbon_emissions_readings", ["organization_id", "source"], unique=False)

    bind = op.get_bind()
    permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": PERMISSION_KEY}).scalar()
    if permission_id is None:
        permission_id = bind.execute(
            sa.text(
                """
                INSERT INTO permissions (id, key, description)
                VALUES (:id, :key, :description)
                RETURNING id
                """
            ),
            {"id": str(uuid.uuid4()), "key": PERMISSION_KEY, "description": PERMISSION_DESCRIPTION},
        ).scalar_one()
    role_ids = bind.execute(sa.text("SELECT id FROM roles WHERE name IN ('owner', 'admin', 'compliance_manager') AND is_active = TRUE")).scalars().all()
    for role_id in role_ids:
        exists = bind.execute(
            sa.text("SELECT 1 FROM role_permissions WHERE role_id = :role_id AND permission_id = :permission_id"),
            {"role_id": role_id, "permission_id": permission_id},
        ).scalar()
        if exists is None:
            bind.execute(
                sa.text("INSERT INTO role_permissions (id, role_id, permission_id) VALUES (:id, :role_id, :permission_id)"),
                {"id": str(uuid.uuid4()), "role_id": role_id, "permission_id": permission_id},
            )


def downgrade() -> None:
    bind = op.get_bind()
    permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": PERMISSION_KEY}).scalar()
    if permission_id is not None:
        bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id = :permission_id"), {"permission_id": permission_id})
        bind.execute(sa.text("DELETE FROM permissions WHERE id = :permission_id"), {"permission_id": permission_id})
    op.drop_index("ix_carbon_readings_org_source", table_name="carbon_emissions_readings")
    op.drop_index("ix_carbon_readings_org_business_unit", table_name="carbon_emissions_readings")
    op.drop_index("ix_carbon_readings_org_scope_period", table_name="carbon_emissions_readings")
    op.drop_index("ix_carbon_emissions_readings_organization_id", table_name="carbon_emissions_readings")
    op.drop_table("carbon_emissions_readings")
