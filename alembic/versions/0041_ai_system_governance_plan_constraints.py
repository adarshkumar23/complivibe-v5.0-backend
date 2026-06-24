"""ai system governance review plan constraints

Revision ID: 0041_ai_system_governance_plan_constraints
Revises: 0040_ai_system_governance_recurrence_templates
Create Date: 2026-06-19 18:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0041_ai_system_governance_plan_constraints"
down_revision: str | None = "0040_ai_system_governance_recurrence_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_system_governance_review_plan_constraints",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_review_type", sa.String(length=64), nullable=False),
        sa.Column("prerequisite_review_type", sa.String(length=64), nullable=False),
        sa.Column("constraint_type", sa.String(length=32), nullable=False),
        sa.Column("enforcement_mode", sa.String(length=16), nullable=False),
        sa.Column("min_gap_days", sa.Integer(), nullable=True),
        sa.Column("max_gap_days", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["archived_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_governance_review_plan_constraints_organization_id",
        "ai_system_governance_review_plan_constraints",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_plan_constraints_org_status",
        "ai_system_governance_review_plan_constraints",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_plan_constraints_org_target",
        "ai_system_governance_review_plan_constraints",
        ["organization_id", "target_review_type"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_plan_constraints_org_prereq",
        "ai_system_governance_review_plan_constraints",
        ["organization_id", "prerequisite_review_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_sys_gov_plan_constraints_org_prereq",
        table_name="ai_system_governance_review_plan_constraints",
    )
    op.drop_index(
        "ix_ai_sys_gov_plan_constraints_org_target",
        table_name="ai_system_governance_review_plan_constraints",
    )
    op.drop_index(
        "ix_ai_sys_gov_plan_constraints_org_status",
        table_name="ai_system_governance_review_plan_constraints",
    )
    op.drop_index(
        "ix_ai_system_governance_review_plan_constraints_organization_id",
        table_name="ai_system_governance_review_plan_constraints",
    )
    op.drop_table("ai_system_governance_review_plan_constraints")
