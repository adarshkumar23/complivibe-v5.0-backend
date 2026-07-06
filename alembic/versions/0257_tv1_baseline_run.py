"""add tv1 baseline run and evidence sync tables

Revision ID: 0257_tv1_baseline_run
Revises: 0256_issue_sync_i3
Create Date: 2026-07-06
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0257_tv1_baseline_run"
down_revision: str | None = "0256_issue_sync_i3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "compliance_baseline_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'running'")),
        sa.Column("selected_framework_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("intake_session_id", sa.Uuid(), nullable=True),
        sa.Column("integration_provider", sa.String(length=32), nullable=True),
        sa.Column("gap_report_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.CheckConstraint("status IN ('running','completed','failed')", name="ck_compliance_baseline_runs_status"),
        sa.CheckConstraint(
            "integration_provider IN ('github','aws','okta') OR integration_provider IS NULL",
            name="ck_compliance_baseline_runs_provider",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["intake_session_id"], ["inbound_questionnaire_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_compliance_baseline_runs_org_status",
        "compliance_baseline_runs",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_compliance_baseline_runs_org_created",
        "compliance_baseline_runs",
        ["organization_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "compliance_baseline_evidence_sync_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("baseline_run_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'running'")),
        sa.Column("collected_evidence_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("details_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.String(length=500), nullable=True),
        sa.CheckConstraint("provider IN ('github','aws','okta')", name="ck_compliance_baseline_sync_runs_provider"),
        sa.CheckConstraint("status IN ('running','completed','failed')", name="ck_compliance_baseline_sync_runs_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["baseline_run_id"], ["compliance_baseline_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_compliance_baseline_sync_runs_org_provider",
        "compliance_baseline_evidence_sync_runs",
        ["organization_id", "provider"],
        unique=False,
    )
    op.create_index(
        "ix_compliance_baseline_sync_runs_baseline",
        "compliance_baseline_evidence_sync_runs",
        ["baseline_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_compliance_baseline_sync_runs_baseline", table_name="compliance_baseline_evidence_sync_runs")
    op.drop_index("ix_compliance_baseline_sync_runs_org_provider", table_name="compliance_baseline_evidence_sync_runs")
    op.drop_table("compliance_baseline_evidence_sync_runs")
    op.drop_index("ix_compliance_baseline_runs_org_created", table_name="compliance_baseline_runs")
    op.drop_index("ix_compliance_baseline_runs_org_status", table_name="compliance_baseline_runs")
    op.drop_table("compliance_baseline_runs")
