"""sso configs table

Revision ID: 0162_sso_configs_table
Revises: 0161_mitre_atlas_seed
Create Date: 2026-06-28 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0162_sso_configs_table"
down_revision: str | None = "0161_mitre_atlas_seed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DEFAULT_ATTRIBUTE_MAPPING = (
    '{"email": "NameID", "first_name": "firstName", "last_name": "lastName", "role": "groups"}'
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("sso_configs"):
        return

    op.create_table(
        "sso_configs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("provider", sa.VARCHAR(length=30), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("sso_url", sa.Text(), nullable=False),
        sa.Column("slo_url", sa.Text(), nullable=True),
        sa.Column("certificate", sa.Text(), nullable=False),
        sa.Column(
            "attribute_mapping",
            sa.JSON(),
            nullable=False,
            server_default=sa.text(f"'{DEFAULT_ATTRIBUTE_MAPPING}'"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("jit_provisioning", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("default_role", sa.VARCHAR(length=30), nullable=False, server_default=sa.text("'member'")),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "provider IN ('okta', 'azure_ad', 'google', 'adfs', 'saml2')",
            name="ck_sso_configs_provider",
        ),
    )

    op.create_index("ix_sso_configs_org_active", "sso_configs", ["organization_id", "is_active"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("sso_configs"):
        op.drop_index("ix_sso_configs_org_active", table_name="sso_configs")
        op.drop_table("sso_configs")
