"""user sessions and org ip allowlist

Revision ID: 0196_user_sessions_and_org_ip_allowlist
Revises: 0195_custom_roles_extend_roles_table
Create Date: 2026-07-02 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0196_user_sessions_and_org_ip_allowlist"
down_revision: str | None = "0195_custom_roles_extend_roles_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_id", sa.String(length=100), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint("status IN ('active', 'revoked', 'expired')", name="ck_user_sessions_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revoked_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_id", name="uq_user_sessions_token_id"),
    )
    op.create_index("ix_user_sessions_org_user", "user_sessions", ["organization_id", "user_id"], unique=False)
    op.create_index("ix_user_sessions_org_status", "user_sessions", ["organization_id", "status"], unique=False)
    op.create_index("ix_user_sessions_user_status", "user_sessions", ["user_id", "status"], unique=False)
    op.create_index("ix_user_sessions_token_id", "user_sessions", ["token_id"], unique=False)

    op.create_table(
        "org_ip_allowlist",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("cidr_range", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_org_ip_allowlist_org_active", "org_ip_allowlist", ["organization_id", "is_active"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_org_ip_allowlist_org_active", table_name="org_ip_allowlist")
    op.drop_table("org_ip_allowlist")

    op.drop_index("ix_user_sessions_token_id", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_status", table_name="user_sessions")
    op.drop_index("ix_user_sessions_org_status", table_name="user_sessions")
    op.drop_index("ix_user_sessions_org_user", table_name="user_sessions")
    op.drop_table("user_sessions")
