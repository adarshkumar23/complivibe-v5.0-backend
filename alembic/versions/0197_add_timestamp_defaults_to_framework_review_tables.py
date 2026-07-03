"""add timestamp defaults to framework review tables

Revision ID: 0197_add_timestamp_defaults_to_framework_review_tables
Revises: 0196_user_sessions_and_org_ip_allowlist
Create Date: 2026-07-03 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0197_add_timestamp_defaults_to_framework_review_tables"
down_revision: str | None = "0196_user_sessions_and_org_ip_allowlist"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 11 tables from migrations 0025-0028 define created_at/updated_at as
# nullable=False with no server_default. The TimestampMixin in the ORM expects
# the database to supply these values on insert when the application does not
# populate them. This migration adds a server_default to every affected column.
TABLE_COLUMNS: list[tuple[str, list[str]]] = [
    # 0025_framework_pack_review_promotion
    ("framework_pack_review_runs", ["created_at", "updated_at"]),
    ("framework_pack_review_signoffs", ["created_at", "updated_at"]),
    ("framework_pack_promotion_requests", ["created_at", "updated_at"]),
    # 0026_framework_review_assignments_sla
    ("framework_pack_review_assignments", ["created_at", "updated_at"]),
    ("framework_review_sla_policies", ["created_at", "updated_at"]),
    ("framework_review_escalation_events", ["created_at", "updated_at"]),
    # 0027_framework_review_capacity_and_suggestions
    ("framework_reviewer_capacity_policies", ["created_at", "updated_at"]),
    ("framework_reviewer_workload_snapshots", ["created_at"]),
    ("framework_review_assignment_suggestions", ["created_at", "updated_at"]),
    # 0028_framework_review_batch_assignments
    ("framework_review_batch_assignment_runs", ["created_at", "updated_at"]),
    ("framework_review_batch_assignment_items", ["created_at"]),
]


def _timestamp_default() -> sa.TextClause:
    # sa.func.now() compiles to now() on PostgreSQL and CURRENT_TIMESTAMP on
    # SQLite, keeping the migration safe to run against both dialects.
    return sa.func.now()


def upgrade() -> None:
    default = _timestamp_default()
    for table_name, columns in TABLE_COLUMNS:
        for column_name in columns:
            op.alter_column(
                table_name,
                column_name,
                existing_type=sa.DateTime(timezone=True),
                existing_nullable=False,
                server_default=default,
            )


def downgrade() -> None:
    for table_name, columns in TABLE_COLUMNS:
        for column_name in columns:
            op.alter_column(
                table_name,
                column_name,
                existing_type=sa.DateTime(timezone=True),
                existing_nullable=False,
                server_default=None,
            )
