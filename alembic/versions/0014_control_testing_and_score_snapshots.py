"""control testing and score snapshot materialization foundation

Revision ID: 0014_control_testing_and_score_snapshots
Revises: 0013_automation_schedule_and_versions
Create Date: 2026-06-18 18:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0014_control_testing_and_score_snapshots"
down_revision: Union[str, Sequence[str], None] = "0013_automation_schedule_and_versions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "control_test_definitions",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("control_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("test_type", sa.String(length=64), nullable=False),
        sa.Column("check_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("cadence", sa.String(length=32), nullable=False, server_default="none"),
        sa.Column("next_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["control_id"], ["controls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_control_test_def_org_control", "control_test_definitions", ["organization_id", "control_id"], unique=False)
    op.create_index("ix_control_test_def_org_status", "control_test_definitions", ["organization_id", "status"], unique=False)
    op.create_index("ix_control_test_def_org_due", "control_test_definitions", ["organization_id", "next_due_at"], unique=False)

    op.create_table(
        "control_test_runs",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("control_test_definition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("control_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("result_reason", sa.Text(), nullable=True),
        sa.Column("check_key", sa.String(length=64), nullable=False),
        sa.Column("executed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("execution_source", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("evidence_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["control_test_definition_id"], ["control_test_definitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["control_id"], ["controls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["executed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["evidence_item_id"], ["evidence_items.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_control_test_runs_org_test", "control_test_runs", ["organization_id", "control_test_definition_id"], unique=False)
    op.create_index("ix_control_test_runs_org_control", "control_test_runs", ["organization_id", "control_id"], unique=False)
    op.create_index("ix_control_test_runs_org_created", "control_test_runs", ["organization_id", "created_at"], unique=False)

    op.add_column("score_snapshots", sa.Column("snapshot_type", sa.String(length=64), nullable=False, server_default="compliance_readiness"))
    op.add_column("score_snapshots", sa.Column("grade", sa.String(length=8), nullable=False, server_default="F"))
    op.add_column(
        "score_snapshots",
        sa.Column("inputs_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "score_snapshots",
        sa.Column("breakdown_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "score_snapshots",
        sa.Column("recommendations_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("score_snapshots", sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))
    op.add_column("score_snapshots", sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))

    op.create_foreign_key(
        "fk_score_snapshots_created_by_user_id_users",
        "score_snapshots",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_score_snapshots_org_type_calc", "score_snapshots", ["organization_id", "snapshot_type", "calculated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_score_snapshots_org_type_calc", table_name="score_snapshots")
    op.drop_constraint("fk_score_snapshots_created_by_user_id_users", "score_snapshots", type_="foreignkey")
    op.drop_column("score_snapshots", "created_by_user_id")
    op.drop_column("score_snapshots", "calculated_at")
    op.drop_column("score_snapshots", "recommendations_json")
    op.drop_column("score_snapshots", "breakdown_json")
    op.drop_column("score_snapshots", "inputs_json")
    op.drop_column("score_snapshots", "grade")
    op.drop_column("score_snapshots", "snapshot_type")

    op.drop_index("ix_control_test_runs_org_created", table_name="control_test_runs")
    op.drop_index("ix_control_test_runs_org_control", table_name="control_test_runs")
    op.drop_index("ix_control_test_runs_org_test", table_name="control_test_runs")
    op.drop_table("control_test_runs")

    op.drop_index("ix_control_test_def_org_due", table_name="control_test_definitions")
    op.drop_index("ix_control_test_def_org_status", table_name="control_test_definitions")
    op.drop_index("ix_control_test_def_org_control", table_name="control_test_definitions")
    op.drop_table("control_test_definitions")
