"""ai risk assessment foundation

Revision ID: 0065_ai_risk_assessment_foundation
Revises: 0064_diag_export_diff_gating_compare_preset_assignments
Create Date: 2026-06-20 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0065_ai_risk_assessment_foundation"
down_revision: str | None = "0064_diag_export_diff_gating_compare_preset_assignments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_system_risk_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("assessment_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("likelihood", sa.String(length=32), nullable=False),
        sa.Column("impact", sa.String(length=32), nullable=False),
        sa.Column("inherent_risk_score", sa.Integer(), nullable=True),
        sa.Column("residual_risk_score", sa.Integer(), nullable=True),
        sa.Column("risk_dimensions_json", sa.JSON(), nullable=True),
        sa.Column("risk_factors_json", sa.JSON(), nullable=True),
        sa.Column("mitigation_summary", sa.Text(), nullable=True),
        sa.Column("assumptions", sa.Text(), nullable=True),
        sa.Column("limitations", sa.Text(), nullable=True),
        sa.Column("methodology_version", sa.String(length=64), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["archived_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_risk_assessments_organization_id",
        "ai_system_risk_assessments",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_risk_assessments_org_ai_system",
        "ai_system_risk_assessments",
        ["organization_id", "ai_system_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_risk_assessments_org_status",
        "ai_system_risk_assessments",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_risk_assessments_org_risk_level",
        "ai_system_risk_assessments",
        ["organization_id", "risk_level"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_risk_assessments_org_type",
        "ai_system_risk_assessments",
        ["organization_id", "assessment_type"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_risk_assessments_org_owner",
        "ai_system_risk_assessments",
        ["organization_id", "owner_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_risk_assessments_org_archived",
        "ai_system_risk_assessments",
        ["organization_id", "archived_at"],
        unique=False,
    )

    op.create_table(
        "ai_system_risk_assessment_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("risk_assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_type", sa.String(length=64), nullable=False),
        sa.Column("snapshot_version", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("snapshot_sha256", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["risk_assessment_id"], ["ai_system_risk_assessments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_risk_assessment_snapshots_organization_id",
        "ai_system_risk_assessment_snapshots",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_risk_assessment_snapshots_org_assessment",
        "ai_system_risk_assessment_snapshots",
        ["organization_id", "risk_assessment_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_risk_assessment_snapshots_org_ai_system",
        "ai_system_risk_assessment_snapshots",
        ["organization_id", "ai_system_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_risk_assessment_snapshots_org_type",
        "ai_system_risk_assessment_snapshots",
        ["organization_id", "snapshot_type"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_risk_assessment_snapshots_org_assessment_version",
        "ai_system_risk_assessment_snapshots",
        ["organization_id", "risk_assessment_id", "snapshot_version"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_system_risk_assessment_snapshots_org_assessment_version",
        table_name="ai_system_risk_assessment_snapshots",
    )
    op.drop_index(
        "ix_ai_system_risk_assessment_snapshots_org_type",
        table_name="ai_system_risk_assessment_snapshots",
    )
    op.drop_index(
        "ix_ai_system_risk_assessment_snapshots_org_ai_system",
        table_name="ai_system_risk_assessment_snapshots",
    )
    op.drop_index(
        "ix_ai_system_risk_assessment_snapshots_org_assessment",
        table_name="ai_system_risk_assessment_snapshots",
    )
    op.drop_index(
        "ix_ai_system_risk_assessment_snapshots_organization_id",
        table_name="ai_system_risk_assessment_snapshots",
    )
    op.drop_table("ai_system_risk_assessment_snapshots")

    op.drop_index("ix_ai_system_risk_assessments_org_archived", table_name="ai_system_risk_assessments")
    op.drop_index("ix_ai_system_risk_assessments_org_owner", table_name="ai_system_risk_assessments")
    op.drop_index("ix_ai_system_risk_assessments_org_type", table_name="ai_system_risk_assessments")
    op.drop_index("ix_ai_system_risk_assessments_org_risk_level", table_name="ai_system_risk_assessments")
    op.drop_index("ix_ai_system_risk_assessments_org_status", table_name="ai_system_risk_assessments")
    op.drop_index("ix_ai_system_risk_assessments_org_ai_system", table_name="ai_system_risk_assessments")
    op.drop_index("ix_ai_system_risk_assessments_organization_id", table_name="ai_system_risk_assessments")
    op.drop_table("ai_system_risk_assessments")
