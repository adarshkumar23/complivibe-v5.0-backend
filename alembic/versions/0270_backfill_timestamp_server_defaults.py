"""backfill missing created_at/updated_at server defaults across all tables

Several early migrations created `created_at`/`updated_at` as NOT NULL columns
without a DB-level `server_default`, even though the corresponding ORM models
declare `server_default=func.now()` (via `TimestampMixin` or directly). Any
code path that lazily inserts a row without explicitly setting these columns
(e.g. `AISystemRiskAssessmentService._governance_settings_for_org`) then hits
a NotNullViolation at flush time, because SQLAlchemy relies on the DB default
firing rather than sending a client-side value for `server_default` columns.

This migration is a systemic fix for that whole bug class (found via a
migration-versus-model sweep across all of alembic/versions/*.py):
  (a) sets `server_default now()` at the DB level for every affected
      created_at/updated_at column so future inserts never violate NOT NULL, and
  (b) backfills any existing NULL rows (shouldn't exist on a healthy DB, but
      defensively handled) using the row's other timestamp column when
      available, falling back to now().

Revision ID: 0270_backfill_timestamp_server_defaults
Revises: 0269_attestation_token_revocation
Create Date: 2026-07-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0270_backfill_timestamp_server_defaults"
down_revision: str | None = "0269_attestation_token_revocation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (table_name, [column_names_present_on_the_table]) for every table whose
# created_at/updated_at columns were created without server_default in their
# originating migration. Columns are listed together so the backfill can use
# whichever sibling timestamp is available as the more-accurate fallback.
_TABLES: list[tuple[str, list[str]]] = [
    ("automation_action_logs", ["created_at"]),
    ("automation_rule_versions", ["created_at"]),
    ("control_test_runs", ["created_at"]),
    ("recertification_action_logs", ["created_at"]),
    ("compliance_report_sections", ["created_at"]),
    ("export_job_events", ["created_at"]),
    ("export_attestations", ["created_at"]),
    ("governance_override_approvals", ["created_at"]),
    ("governance_override_events", ["created_at"]),
    ("governance_override_template_versions", ["created_at"]),
    ("obligation_content_versions", ["created_at"]),
    ("applicability_evaluation_runs", ["created_at"]),
    ("applicability_evaluation_results", ["created_at"]),
    ("framework_pack_review_runs", ["created_at", "updated_at"]),
    ("framework_pack_review_signoffs", ["created_at", "updated_at"]),
    ("framework_pack_promotion_requests", ["created_at", "updated_at"]),
    ("framework_pack_review_assignments", ["created_at", "updated_at"]),
    ("framework_review_sla_policies", ["created_at", "updated_at"]),
    ("framework_review_escalation_events", ["created_at", "updated_at"]),
    ("framework_reviewer_capacity_policies", ["created_at", "updated_at"]),
    ("framework_reviewer_workload_snapshots", ["created_at"]),
    ("framework_review_assignment_suggestions", ["created_at", "updated_at"]),
    ("framework_review_batch_assignment_runs", ["created_at", "updated_at"]),
    ("framework_review_batch_assignment_items", ["created_at"]),
    ("framework_review_batch_cancellation_requests", ["created_at", "updated_at"]),
    ("organization_governance_settings", ["created_at", "updated_at"]),
    ("organization_governance_setting_history", ["created_at"]),
    ("organization_governance_manifest_verification_events", ["created_at"]),
    ("data_obligation_suggestions", ["created_at", "updated_at"]),
    ("llm_observability_events", ["created_at"]),
    ("governance_autopilot_executions", ["created_at", "updated_at"]),
    ("issue_policy_links", ["created_at"]),
]


def upgrade() -> None:
    conn = op.get_bind()
    for table, columns in _TABLES:
        for column in columns:
            op.alter_column(
                table,
                column,
                server_default=sa.text("now()"),
                existing_type=sa.DateTime(timezone=True),
            )
        # Backfill any lingering NULLs. Prefer the sibling timestamp column
        # (more accurate than "now") when the row has one and it's populated,
        # otherwise fall back to now().
        if "created_at" in columns and "updated_at" in columns:
            conn.execute(
                sa.text(
                    f'UPDATE "{table}" SET created_at = COALESCE(created_at, updated_at, now()) '
                    "WHERE created_at IS NULL"
                )
            )
            conn.execute(
                sa.text(
                    f'UPDATE "{table}" SET updated_at = COALESCE(updated_at, created_at, now()) '
                    "WHERE updated_at IS NULL"
                )
            )
        else:
            for column in columns:
                conn.execute(
                    sa.text(f'UPDATE "{table}" SET {column} = now() WHERE {column} IS NULL')
                )


def downgrade() -> None:
    for table, columns in _TABLES:
        for column in columns:
            op.alter_column(
                table,
                column,
                server_default=None,
                existing_type=sa.DateTime(timezone=True),
            )
