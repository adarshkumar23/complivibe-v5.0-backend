"""recertification workflow and scoring trend support

Revision ID: 0015_recertification_and_scoring_trends
Revises: 0014_control_testing_and_score_snapshots
Create Date: 2026-06-18 20:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0015_recertification_and_scoring_trends"
down_revision: Union[str, Sequence[str], None] = "0014_control_testing_and_score_snapshots"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "evidence_recertification_policies",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("scope_config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("cadence", sa.String(length=32), nullable=False),
        sa.Column("lead_time_days", sa.Integer(), nullable=False, server_default="14"),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recert_policy_org_status", "evidence_recertification_policies", ["organization_id", "status"], unique=False)
    op.create_index("ix_recert_policy_org_next_run", "evidence_recertification_policies", ["organization_id", "next_run_at"], unique=False)

    op.create_table(
        "recertification_runs",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("run_type", sa.String(length=32), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("overdue_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("task_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("email_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_id"], ["evidence_recertification_policies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recert_run_org_type", "recertification_runs", ["organization_id", "run_type"], unique=False)
    op.create_index("ix_recert_run_org_status", "recertification_runs", ["organization_id", "status"], unique=False)
    op.create_index("ix_recert_run_org_created", "recertification_runs", ["organization_id", "created_at"], unique=False)

    op.create_table(
        "recertification_action_logs",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("action_status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("created_task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_email_outbox_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("skipped_reason", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["recertification_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_id"], ["evidence_recertification_policies.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_recert_action_idempotency"),
    )
    op.create_index("ix_recert_action_org_run", "recertification_action_logs", ["organization_id", "run_id"], unique=False)
    op.create_index("ix_recert_action_org_status", "recertification_action_logs", ["organization_id", "action_status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_recert_action_org_status", table_name="recertification_action_logs")
    op.drop_index("ix_recert_action_org_run", table_name="recertification_action_logs")
    op.drop_table("recertification_action_logs")

    op.drop_index("ix_recert_run_org_created", table_name="recertification_runs")
    op.drop_index("ix_recert_run_org_status", table_name="recertification_runs")
    op.drop_index("ix_recert_run_org_type", table_name="recertification_runs")
    op.drop_table("recertification_runs")

    op.drop_index("ix_recert_policy_org_next_run", table_name="evidence_recertification_policies")
    op.drop_index("ix_recert_policy_org_status", table_name="evidence_recertification_policies")
    op.drop_table("evidence_recertification_policies")
