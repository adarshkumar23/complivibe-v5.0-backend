"""add evidence automation rule health tracking and ingest idempotency

Revision ID: 0266_evidence_automation_health_idempotency
Revises: 0265_baseline_run_single_running_guard
Create Date: 2026-07-08

Adds rule-health tracking columns (last_triggered_at, last_matched_at,
trigger_count, consecutive_error_count, last_error_at, last_error_message) to
evidence_automation_rules so stale/broken connectors can be surfaced, and a
new evidence_automation_ingest_events table that records every processed
ingest event per rule so duplicate webhook/email/form retries can be
deduplicated by idempotency key instead of silently creating duplicate
evidence items.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0266_evidence_automation_health_idempotency"
down_revision: str | None = "0265_baseline_run_single_running_guard"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evidence_automation_rules",
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "evidence_automation_rules",
        sa.Column("last_matched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "evidence_automation_rules",
        sa.Column("trigger_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "evidence_automation_rules",
        sa.Column("consecutive_error_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "evidence_automation_rules",
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "evidence_automation_rules",
        sa.Column("last_error_message", sa.Text(), nullable=True),
    )

    op.create_table(
        "evidence_automation_ingest_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("automation_rule_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("evidence_item_id", sa.Uuid(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('created','duplicate','error')",
            name="ck_evidence_automation_ingest_events_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["automation_rule_id"], ["evidence_automation_rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_item_id"], ["evidence_items.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evidence_automation_ingest_events_org_rule",
        "evidence_automation_ingest_events",
        ["organization_id", "automation_rule_id"],
        unique=False,
    )
    # Partial unique index: only enforce dedupe when an idempotency key was resolved.
    op.create_index(
        "uq_evidence_automation_ingest_events_rule_key",
        "evidence_automation_ingest_events",
        ["automation_rule_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_evidence_automation_ingest_events_rule_key", table_name="evidence_automation_ingest_events")
    op.drop_index("ix_evidence_automation_ingest_events_org_rule", table_name="evidence_automation_ingest_events")
    op.drop_table("evidence_automation_ingest_events")

    op.drop_column("evidence_automation_rules", "last_error_message")
    op.drop_column("evidence_automation_rules", "last_error_at")
    op.drop_column("evidence_automation_rules", "consecutive_error_count")
    op.drop_column("evidence_automation_rules", "trigger_count")
    op.drop_column("evidence_automation_rules", "last_matched_at")
    op.drop_column("evidence_automation_rules", "last_triggered_at")
