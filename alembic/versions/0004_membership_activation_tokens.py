"""add membership activation tokens

Revision ID: 0004_membership_activation_tokens
Revises: 0003_membership_user_status
Create Date: 2026-06-18 01:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004_membership_activation_tokens"
down_revision: Union[str, Sequence[str], None] = "0003_membership_user_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "membership_activation_tokens",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["membership_id"], ["memberships.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )

    op.create_index(
        "ix_membership_activation_tokens_organization_id",
        "membership_activation_tokens",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_membership_activation_tokens_membership_id",
        "membership_activation_tokens",
        ["membership_id"],
        unique=False,
    )
    op.create_index(
        "ix_membership_activation_tokens_user_id",
        "membership_activation_tokens",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_membership_activation_tokens_status",
        "membership_activation_tokens",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_membership_activation_tokens_expires_at",
        "membership_activation_tokens",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_membership_activation_tokens_token_hash",
        "membership_activation_tokens",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_membership_activation_tokens_token_hash", table_name="membership_activation_tokens")
    op.drop_index("ix_membership_activation_tokens_expires_at", table_name="membership_activation_tokens")
    op.drop_index("ix_membership_activation_tokens_status", table_name="membership_activation_tokens")
    op.drop_index("ix_membership_activation_tokens_user_id", table_name="membership_activation_tokens")
    op.drop_index("ix_membership_activation_tokens_membership_id", table_name="membership_activation_tokens")
    op.drop_index("ix_membership_activation_tokens_organization_id", table_name="membership_activation_tokens")
    op.drop_table("membership_activation_tokens")
