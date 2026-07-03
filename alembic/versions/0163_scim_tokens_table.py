"""scim tokens table

Revision ID: 0163_scim_tokens_table
Revises: 0162_sso_configs_table
Create Date: 2026-06-28 14:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0163_scim_tokens_table"
down_revision: str | None = "0162_sso_configs_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("scim_tokens"):
        return

    op.create_table(
        "scim_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.VARCHAR(length=64), nullable=False),
        sa.Column("description", sa.VARCHAR(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_scim_tokens_org_active", "scim_tokens", ["organization_id", "is_active"], unique=False)
    op.create_index("ix_scim_tokens_token_hash", "scim_tokens", ["token_hash"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("scim_tokens"):
        op.drop_index("ix_scim_tokens_token_hash", table_name="scim_tokens")
        op.drop_index("ix_scim_tokens_org_active", table_name="scim_tokens")
        op.drop_table("scim_tokens")
