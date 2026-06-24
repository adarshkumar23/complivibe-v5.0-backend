"""diagnostic export diff gating compare preset assignments

Revision ID: 0064_diag_export_diff_gating_compare_preset_assignments
Revises: 0063_diag_export_diff_gating_compare_preset_versions
Create Date: 2026-06-20 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0064_diag_export_diff_gating_compare_preset_assignments"
down_revision: str | None = "0063_diag_export_diff_gating_compare_preset_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("preset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope_type", sa.String(length=64), nullable=False),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("scope_json", sa.JSON(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("assigned_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["preset_id"],
            ["ai_system_governance_diagnostic_export_diff_gating_compare_presets.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["assigned_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["archived_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_governance_diag_export_diff_gating_cmp_preset_assignments_organization_id",
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignments",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_assign_org_status",
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignments",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_assign_org_scope",
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignments",
        ["organization_id", "scope_type"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_assign_org_preset",
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignments",
        ["organization_id", "preset_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_assign_org_priority",
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignments",
        ["organization_id", "priority"],
        unique=False,
    )

    op.create_table(
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignment_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("changed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignments.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_governance_diag_export_diff_gating_cmp_preset_assign_hist_organization_id",
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignment_history",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_assign_hist_org_assignment",
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignment_history",
        ["organization_id", "assignment_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_assign_hist_org_event",
        "ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignment_history",
        ["organization_id", "event_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_assign_hist_org_event",
        table_name="ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignment_history",
    )
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_assign_hist_org_assignment",
        table_name="ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignment_history",
    )
    op.drop_index(
        "ix_ai_system_governance_diag_export_diff_gating_cmp_preset_assign_hist_organization_id",
        table_name="ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignment_history",
    )
    op.drop_table("ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignment_history")

    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_assign_org_priority",
        table_name="ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignments",
    )
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_assign_org_preset",
        table_name="ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignments",
    )
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_assign_org_scope",
        table_name="ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignments",
    )
    op.drop_index(
        "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_assign_org_status",
        table_name="ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignments",
    )
    op.drop_index(
        "ix_ai_system_governance_diag_export_diff_gating_cmp_preset_assignments_organization_id",
        table_name="ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignments",
    )
    op.drop_table("ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignments")
