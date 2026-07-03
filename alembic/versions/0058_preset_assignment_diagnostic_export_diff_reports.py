"""preset assignment diagnostic export diff reports

Revision ID: 0058_preset_assignment_diagnostic_export_diff_reports
Revises: 0057_preset_assignment_diagnostic_exports
Create Date: 2026-06-20 01:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0058_preset_assignment_diagnostic_export_diff_reports"
down_revision: str | None = "0057_preset_assignment_diagnostic_exports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_system_gov_pst_assign_diag_export_diff_rpts_29e68c83",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("base_export_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("compare_export_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("export_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("diff_json", sa.JSON(), nullable=False),
        sa.Column("base_canonical_payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("compare_canonical_payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("payload_hash_changed", sa.Boolean(), nullable=False),
        sa.Column("base_valid_signature", sa.Boolean(), nullable=False),
        sa.Column("compare_valid_signature", sa.Boolean(), nullable=False),
        sa.Column("base_trusted", sa.Boolean(), nullable=False),
        sa.Column("compare_trusted", sa.Boolean(), nullable=False),
        sa.Column("added_paths_count", sa.Integer(), nullable=False),
        sa.Column("removed_paths_count", sa.Integer(), nullable=False),
        sa.Column("changed_paths_count", sa.Integer(), nullable=False),
        sa.Column("unchanged_paths_count", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["base_export_id"],
            ["ai_system_governance_preset_assignment_diagnostic_exports.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["compare_export_id"],
            ["ai_system_governance_preset_assignment_diagnostic_exports.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["archived_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_gov_pst_assign_diag_export_diff_rpts_29e_7a807fd3",
        "ai_system_gov_pst_assign_diag_export_diff_rpts_29e68c83",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_preset_assign_diag_export_diff_org_status",
        "ai_system_gov_pst_assign_diag_export_diff_rpts_29e68c83",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_preset_assign_diag_export_diff_org_type",
        "ai_system_gov_pst_assign_diag_export_diff_rpts_29e68c83",
        ["organization_id", "export_type"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_preset_assign_diag_export_diff_org_base",
        "ai_system_gov_pst_assign_diag_export_diff_rpts_29e68c83",
        ["organization_id", "base_export_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_preset_assign_diag_export_diff_org_compare",
        "ai_system_gov_pst_assign_diag_export_diff_rpts_29e68c83",
        ["organization_id", "compare_export_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_preset_assign_diag_export_diff_org_created",
        "ai_system_gov_pst_assign_diag_export_diff_rpts_29e68c83",
        ["organization_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_sys_gov_preset_assign_diag_export_diff_org_created",
        table_name="ai_system_gov_pst_assign_diag_export_diff_rpts_29e68c83",
    )
    op.drop_index(
        "ix_ai_sys_gov_preset_assign_diag_export_diff_org_compare",
        table_name="ai_system_gov_pst_assign_diag_export_diff_rpts_29e68c83",
    )
    op.drop_index(
        "ix_ai_sys_gov_preset_assign_diag_export_diff_org_base",
        table_name="ai_system_gov_pst_assign_diag_export_diff_rpts_29e68c83",
    )
    op.drop_index(
        "ix_ai_sys_gov_preset_assign_diag_export_diff_org_type",
        table_name="ai_system_gov_pst_assign_diag_export_diff_rpts_29e68c83",
    )
    op.drop_index(
        "ix_ai_sys_gov_preset_assign_diag_export_diff_org_status",
        table_name="ai_system_gov_pst_assign_diag_export_diff_rpts_29e68c83",
    )
    op.drop_index(
        "ix_ai_system_gov_pst_assign_diag_export_diff_rpts_29e_7a807fd3",
        table_name="ai_system_gov_pst_assign_diag_export_diff_rpts_29e68c83",
    )
    op.drop_table("ai_system_gov_pst_assign_diag_export_diff_rpts_29e68c83")
