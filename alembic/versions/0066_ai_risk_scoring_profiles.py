"""ai risk scoring profiles

Revision ID: 0066_ai_risk_scoring_profiles
Revises: 0065_ai_risk_assessment_foundation
Create Date: 2026-06-20 17:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0066_ai_risk_scoring_profiles"
down_revision: str | None = "0065_ai_risk_assessment_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_system_risk_scoring_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("likelihood_weights_json", sa.JSON(), nullable=False),
        sa.Column("impact_weights_json", sa.JSON(), nullable=False),
        sa.Column("risk_level_thresholds_json", sa.JSON(), nullable=False),
        sa.Column("methodology_version", sa.String(length=64), nullable=False),
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
        "ix_ai_system_risk_scoring_profiles_organization_id",
        "ai_system_risk_scoring_profiles",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_risk_scoring_profiles_org_status",
        "ai_system_risk_scoring_profiles",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_risk_scoring_profiles_org_default",
        "ai_system_risk_scoring_profiles",
        ["organization_id", "is_default"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_risk_scoring_profiles_org_archived",
        "ai_system_risk_scoring_profiles",
        ["organization_id", "archived_at"],
        unique=False,
    )

    op.add_column("ai_system_risk_assessments", sa.Column("scoring_profile_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("ai_system_risk_assessments", sa.Column("scoring_profile_snapshot_json", sa.JSON(), nullable=True))
    op.add_column("ai_system_risk_assessments", sa.Column("score_explanation_json", sa.JSON(), nullable=True))
    op.add_column("ai_system_risk_assessments", sa.Column("calculated_risk_level", sa.String(length=32), nullable=True))
    op.create_foreign_key(
        "fk_ai_system_risk_assessments_scoring_profile_id",
        "ai_system_risk_assessments",
        "ai_system_risk_scoring_profiles",
        ["scoring_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_ai_system_risk_assessments_org_scoring_profile",
        "ai_system_risk_assessments",
        ["organization_id", "scoring_profile_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_system_risk_assessments_org_calculated_risk_level",
        "ai_system_risk_assessments",
        ["organization_id", "calculated_risk_level"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_system_risk_assessments_org_calculated_risk_level", table_name="ai_system_risk_assessments")
    op.drop_index("ix_ai_system_risk_assessments_org_scoring_profile", table_name="ai_system_risk_assessments")
    op.drop_constraint(
        "fk_ai_system_risk_assessments_scoring_profile_id",
        "ai_system_risk_assessments",
        type_="foreignkey",
    )
    op.drop_column("ai_system_risk_assessments", "calculated_risk_level")
    op.drop_column("ai_system_risk_assessments", "score_explanation_json")
    op.drop_column("ai_system_risk_assessments", "scoring_profile_snapshot_json")
    op.drop_column("ai_system_risk_assessments", "scoring_profile_id")

    op.drop_index("ix_ai_system_risk_scoring_profiles_org_archived", table_name="ai_system_risk_scoring_profiles")
    op.drop_index("ix_ai_system_risk_scoring_profiles_org_default", table_name="ai_system_risk_scoring_profiles")
    op.drop_index("ix_ai_system_risk_scoring_profiles_org_status", table_name="ai_system_risk_scoring_profiles")
    op.drop_index("ix_ai_system_risk_scoring_profiles_organization_id", table_name="ai_system_risk_scoring_profiles")
    op.drop_table("ai_system_risk_scoring_profiles")
