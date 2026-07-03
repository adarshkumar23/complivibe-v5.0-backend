"""preset assignment diagnostic exports

Revision ID: 0057_preset_assignment_diagnostic_exports
Revises: 0056_preset_assignment_diagnostic_reports
Create Date: 2026-06-20 00:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0057_preset_assignment_diagnostic_exports"
down_revision: str | None = "0056_preset_assignment_diagnostic_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_system_governance_preset_assignment_diagnostic_exports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("export_type", sa.String(length=64), nullable=False),
        sa.Column("source_report_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_diff_report_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("export_payload_json", sa.JSON(), nullable=False),
        sa.Column("canonical_payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("signature_algorithm", sa.String(length=64), nullable=False),
        sa.Column("internal_signature", sa.String(length=128), nullable=False),
        sa.Column("signing_key_id", sa.String(length=128), nullable=True),
        sa.Column("exported_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_report_id"],
            ["ai_system_governance_preset_assignment_diagnostic_reports.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_diff_report_id"],
            ["ai_system_governance_preset_assignment_diagnostic_diff_reports.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["exported_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_gov_pst_assign_diag_exports_org_id_138ae610",
        "ai_system_governance_preset_assignment_diagnostic_exports",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_preset_assign_diag_exports_org_status",
        "ai_system_governance_preset_assignment_diagnostic_exports",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_preset_assign_diag_exports_org_type",
        "ai_system_governance_preset_assignment_diagnostic_exports",
        ["organization_id", "export_type"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_preset_assign_diag_exports_org_report",
        "ai_system_governance_preset_assignment_diagnostic_exports",
        ["organization_id", "source_report_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_preset_assign_diag_exports_org_diff",
        "ai_system_governance_preset_assignment_diagnostic_exports",
        ["organization_id", "source_diff_report_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_preset_assign_diag_exports_org_created",
        "ai_system_governance_preset_assignment_diagnostic_exports",
        ["organization_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_sys_gov_preset_assign_diag_exports_org_created",
        table_name="ai_system_governance_preset_assignment_diagnostic_exports",
    )
    op.drop_index(
        "ix_ai_sys_gov_preset_assign_diag_exports_org_diff",
        table_name="ai_system_governance_preset_assignment_diagnostic_exports",
    )
    op.drop_index(
        "ix_ai_sys_gov_preset_assign_diag_exports_org_report",
        table_name="ai_system_governance_preset_assignment_diagnostic_exports",
    )
    op.drop_index(
        "ix_ai_sys_gov_preset_assign_diag_exports_org_type",
        table_name="ai_system_governance_preset_assignment_diagnostic_exports",
    )
    op.drop_index(
        "ix_ai_sys_gov_preset_assign_diag_exports_org_status",
        table_name="ai_system_governance_preset_assignment_diagnostic_exports",
    )
    op.drop_index(
        "ix_ai_system_gov_pst_assign_diag_exports_org_id_138ae610",
        table_name="ai_system_governance_preset_assignment_diagnostic_exports",
    )
    op.drop_table("ai_system_governance_preset_assignment_diagnostic_exports")
