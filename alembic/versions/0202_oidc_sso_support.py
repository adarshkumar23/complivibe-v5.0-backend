"""oidc sso support

Revision ID: 0202_oidc_sso_support
Revises: f37a755f8aa6
Create Date: 2026-07-04 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0202_oidc_sso_support"
down_revision: str | None = "f37a755f8aa6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oidc_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("issuer_url", sa.Text(), nullable=False),
        sa.Column("client_id", sa.Text(), nullable=False),
        sa.Column("client_secret_enc", sa.Text(), nullable=False),
        sa.Column("authorization_endpoint", sa.Text(), nullable=False),
        sa.Column("token_endpoint", sa.Text(), nullable=False),
        sa.Column("jwks_uri", sa.Text(), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False, server_default=sa.text("'[\"openid\", \"email\", \"profile\"]'::json")),
        sa.Column(
            "claim_mapping",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{\"email\": \"email\", \"subject\": \"sub\", \"name\": \"name\"}'::json"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("jit_provisioning", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("default_role", sa.String(length=30), nullable=False, server_default=sa.text("'member'")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("provider IN ('okta', 'azure_ad', 'google', 'auth0', 'oidc')", name="ck_oidc_configs_provider"),
        sa.CheckConstraint(
            "default_role IN ('member', 'reviewer', 'compliance_manager', 'admin', 'owner', 'auditor')",
            name="ck_oidc_configs_default_role",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", name="uq_oidc_configs_org"),
    )
    op.create_index("ix_oidc_configs_org_active", "oidc_configs", ["organization_id", "is_active"], unique=False)
    op.create_index("ix_oidc_configs_organization_id", "oidc_configs", ["organization_id"], unique=False)

    op.create_table(
        "oidc_auth_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("nonce_hash", sa.String(length=64), nullable=False),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_oidc_auth_states_state_hash", "oidc_auth_states", ["state_hash"], unique=True)
    op.create_index("ix_oidc_auth_states_org_expires", "oidc_auth_states", ["organization_id", "expires_at"], unique=False)
    op.create_index("ix_oidc_auth_states_organization_id", "oidc_auth_states", ["organization_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_oidc_auth_states_organization_id", table_name="oidc_auth_states")
    op.drop_index("ix_oidc_auth_states_org_expires", table_name="oidc_auth_states")
    op.drop_index("ix_oidc_auth_states_state_hash", table_name="oidc_auth_states")
    op.drop_table("oidc_auth_states")

    op.drop_index("ix_oidc_configs_organization_id", table_name="oidc_configs")
    op.drop_index("ix_oidc_configs_org_active", table_name="oidc_configs")
    op.drop_table("oidc_configs")
