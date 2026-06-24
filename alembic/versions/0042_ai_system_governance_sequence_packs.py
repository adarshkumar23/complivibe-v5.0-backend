"""ai system governance sequence packs and runs

Revision ID: 0042_ai_system_governance_sequence_packs
Revises: 0041_ai_system_governance_plan_constraints
Create Date: 2026-06-19 19:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0042_ai_system_governance_sequence_packs"
down_revision: str | None = "0041_ai_system_governance_plan_constraints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_system_governance_review_sequence_packs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
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
        "ix_ai_system_governance_review_sequence_packs_organization_id",
        "ai_system_governance_review_sequence_packs",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_seq_packs_org_status",
        "ai_system_governance_review_sequence_packs",
        ["organization_id", "status"],
        unique=False,
    )

    op.create_table(
        "ai_system_governance_review_sequence_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_pack_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("review_type", sa.String(length=64), nullable=False),
        sa.Column("title_template", sa.String(length=255), nullable=True),
        sa.Column("description_template", sa.Text(), nullable=True),
        sa.Column("offset_days_from_start", sa.Integer(), nullable=False),
        sa.Column("default_reminder_policy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("default_assigned_to_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("default_checklist_json", sa.JSON(), nullable=True),
        sa.Column("require_previous_step_planned", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sequence_pack_id"], ["ai_system_governance_review_sequence_packs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["default_assigned_to_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["default_reminder_policy_id"], ["ai_system_governance_review_reminder_policies.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_governance_review_sequence_steps_organization_id",
        "ai_system_governance_review_sequence_steps",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_seq_steps_org_pack",
        "ai_system_governance_review_sequence_steps",
        ["organization_id", "sequence_pack_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_seq_steps_org_status",
        "ai_system_governance_review_sequence_steps",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_seq_steps_org_step_order",
        "ai_system_governance_review_sequence_steps",
        ["organization_id", "sequence_pack_id", "step_order"],
        unique=False,
    )

    op.create_table(
        "ai_system_governance_review_sequence_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_pack_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("target_ai_system_ids_json", sa.JSON(), nullable=True),
        sa.Column("start_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("apply_constraints", sa.Boolean(), nullable=False),
        sa.Column("generated_reviews_count", sa.Integer(), nullable=False),
        sa.Column("skipped_reviews_count", sa.Integer(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sequence_pack_id"], ["ai_system_governance_review_sequence_packs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_governance_review_sequence_runs_organization_id",
        "ai_system_governance_review_sequence_runs",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_seq_runs_org_pack",
        "ai_system_governance_review_sequence_runs",
        ["organization_id", "sequence_pack_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_seq_runs_org_status",
        "ai_system_governance_review_sequence_runs",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_seq_runs_org_created",
        "ai_system_governance_review_sequence_runs",
        ["organization_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_sys_gov_seq_runs_org_created", table_name="ai_system_governance_review_sequence_runs")
    op.drop_index("ix_ai_sys_gov_seq_runs_org_status", table_name="ai_system_governance_review_sequence_runs")
    op.drop_index("ix_ai_sys_gov_seq_runs_org_pack", table_name="ai_system_governance_review_sequence_runs")
    op.drop_index("ix_ai_system_governance_review_sequence_runs_organization_id", table_name="ai_system_governance_review_sequence_runs")
    op.drop_table("ai_system_governance_review_sequence_runs")

    op.drop_index("ix_ai_sys_gov_seq_steps_org_step_order", table_name="ai_system_governance_review_sequence_steps")
    op.drop_index("ix_ai_sys_gov_seq_steps_org_status", table_name="ai_system_governance_review_sequence_steps")
    op.drop_index("ix_ai_sys_gov_seq_steps_org_pack", table_name="ai_system_governance_review_sequence_steps")
    op.drop_index("ix_ai_system_governance_review_sequence_steps_organization_id", table_name="ai_system_governance_review_sequence_steps")
    op.drop_table("ai_system_governance_review_sequence_steps")

    op.drop_index("ix_ai_sys_gov_seq_packs_org_status", table_name="ai_system_governance_review_sequence_packs")
    op.drop_index("ix_ai_system_governance_review_sequence_packs_organization_id", table_name="ai_system_governance_review_sequence_packs")
    op.drop_table("ai_system_governance_review_sequence_packs")
