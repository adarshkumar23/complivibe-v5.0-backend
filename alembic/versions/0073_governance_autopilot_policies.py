"""governance autopilot policy guardrails foundation

Revision ID: 0073_governance_autopilot_policies
Revises: 0072_governance_copilot_draft_snapshots
Create Date: 2026-06-20 23:59:59.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0073_governance_autopilot_policies"
down_revision: str | None = "0072_governance_copilot_draft_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "governance_autopilot_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("mode", sa.String(length=32), nullable=False, server_default="suggest_only"),
        sa.Column("allowed_action_types_json", sa.JSON(), nullable=True),
        sa.Column("blocked_action_types_json", sa.JSON(), nullable=True),
        sa.Column("allowed_draft_types_json", sa.JSON(), nullable=True),
        sa.Column("blocked_draft_types_json", sa.JSON(), nullable=True),
        sa.Column("allowed_signal_reason_codes_json", sa.JSON(), nullable=True),
        sa.Column("blocked_signal_reason_codes_json", sa.JSON(), nullable=True),
        sa.Column("approval_required_action_types_json", sa.JSON(), nullable=True),
        sa.Column("approval_required_priority_bands_json", sa.JSON(), nullable=True),
        sa.Column("max_allowed_priority_band_for_auto", sa.String(length=16), nullable=False, server_default="low"),
        sa.Column("external_effects_allowed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("task_creation_allowed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("review_creation_allowed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("source_record_mutation_allowed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("policy_json", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_governance_autopilot_policies_organization_id",
        "governance_autopilot_policies",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_policies_org_status",
        "governance_autopilot_policies",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_policies_org_default",
        "governance_autopilot_policies",
        ["organization_id", "is_default"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_policies_org_mode",
        "governance_autopilot_policies",
        ["organization_id", "mode"],
        unique=False,
    )
    op.create_index(
        "ix_governance_autopilot_policies_org_created",
        "governance_autopilot_policies",
        ["organization_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_governance_autopilot_policies_org_created", table_name="governance_autopilot_policies")
    op.drop_index("ix_governance_autopilot_policies_org_mode", table_name="governance_autopilot_policies")
    op.drop_index("ix_governance_autopilot_policies_org_default", table_name="governance_autopilot_policies")
    op.drop_index("ix_governance_autopilot_policies_org_status", table_name="governance_autopilot_policies")
    op.drop_index("ix_governance_autopilot_policies_organization_id", table_name="governance_autopilot_policies")
    op.drop_table("governance_autopilot_policies")
