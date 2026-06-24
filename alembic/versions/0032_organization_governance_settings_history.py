"""organization governance settings history

Revision ID: 0032_organization_governance_settings_history
Revises: 0031_organization_governance_settings
Create Date: 2026-06-18 23:55:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0032_organization_governance_settings_history"
down_revision: str | None = "0031_organization_governance_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organization_governance_setting_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("setting_key", sa.String(length=64), nullable=False),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("affected_entity_type", sa.String(length=64), nullable=True),
        sa.Column("affected_entity_ids_json", sa.JSON(), nullable=True),
        sa.Column("skipped_summary_json", sa.JSON(), nullable=True),
        sa.Column("changed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("audit_log_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["audit_log_id"], ["audit_logs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_org_governance_setting_history_org_version",
        "organization_governance_setting_history",
        ["organization_id", "version"],
        unique=True,
    )
    op.create_index(
        "ix_org_governance_setting_history_org_event_created",
        "organization_governance_setting_history",
        ["organization_id", "event_type", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_org_governance_setting_history_org_event_created",
        table_name="organization_governance_setting_history",
    )
    op.drop_index(
        "ix_org_governance_setting_history_org_version",
        table_name="organization_governance_setting_history",
    )
    op.drop_table("organization_governance_setting_history")
