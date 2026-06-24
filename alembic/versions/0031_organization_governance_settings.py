"""organization governance settings defaults

Revision ID: 0031_organization_governance_settings
Revises: 0030_batch_cancellation_dual_approval
Create Date: 2026-06-18 23:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0031_organization_governance_settings"
down_revision: str | None = "0030_batch_cancellation_dual_approval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organization_governance_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_cancellation_requires_approval", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("batch_cancellation_policy_reason", sa.Text(), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_organization_governance_settings_org",
        "organization_governance_settings",
        ["organization_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_organization_governance_settings_org", table_name="organization_governance_settings")
    op.drop_table("organization_governance_settings")
