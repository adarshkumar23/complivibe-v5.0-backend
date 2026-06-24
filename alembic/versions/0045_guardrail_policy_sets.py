"""guardrail policy sets and versions

Revision ID: 0045_guardrail_policy_sets
Revises: 0044_guardrail_precedence_controls
Create Date: 2026-06-19 23:45:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0045_guardrail_policy_sets"
down_revision: str | None = "0044_guardrail_precedence_controls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_system_governance_guardrail_policy_sets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("active_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["archived_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_governance_guardrail_policy_sets_organization_id",
        "ai_system_governance_guardrail_policy_sets",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_guardrail_policy_sets_org_status",
        "ai_system_governance_guardrail_policy_sets",
        ["organization_id", "status"],
        unique=False,
    )

    op.create_table(
        "ai_system_governance_guardrail_policy_set_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_set_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("profile_json", sa.JSON(), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("activated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_set_id"], ["ai_system_governance_guardrail_policy_sets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["activated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_governance_guardrail_policy_set_versions_organization_id",
        "ai_system_governance_guardrail_policy_set_versions",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_guardrail_policy_versions_org_set",
        "ai_system_governance_guardrail_policy_set_versions",
        ["organization_id", "policy_set_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_guardrail_policy_versions_org_status",
        "ai_system_governance_guardrail_policy_set_versions",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_guardrail_policy_versions_org_set_num",
        "ai_system_governance_guardrail_policy_set_versions",
        ["organization_id", "policy_set_id", "version_number"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_sys_gov_guardrail_policy_versions_org_set_num",
        table_name="ai_system_governance_guardrail_policy_set_versions",
    )
    op.drop_index(
        "ix_ai_sys_gov_guardrail_policy_versions_org_status",
        table_name="ai_system_governance_guardrail_policy_set_versions",
    )
    op.drop_index(
        "ix_ai_sys_gov_guardrail_policy_versions_org_set",
        table_name="ai_system_governance_guardrail_policy_set_versions",
    )
    op.drop_index(
        "ix_ai_system_governance_guardrail_policy_set_versions_organization_id",
        table_name="ai_system_governance_guardrail_policy_set_versions",
    )
    op.drop_table("ai_system_governance_guardrail_policy_set_versions")

    op.drop_index(
        "ix_ai_sys_gov_guardrail_policy_sets_org_status",
        table_name="ai_system_governance_guardrail_policy_sets",
    )
    op.drop_index(
        "ix_ai_system_governance_guardrail_policy_sets_organization_id",
        table_name="ai_system_governance_guardrail_policy_sets",
    )
    op.drop_table("ai_system_governance_guardrail_policy_sets")
