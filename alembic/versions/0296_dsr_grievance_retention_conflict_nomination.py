"""add DSR grievance subtype, retention-conflict tracking, and nomination-aware submission

Revision ID: 0296_dsr_grievance_retention_conflict_nomination
Revises: 0295_sdf_designation_suggestions
Create Date: 2026-07-10 00:20:00.000000

DPDP Rules 2025 (Rule 14(3)) caps grievance redressal at ninety days, a separate SLA
track from the general request-response deadline. Erasure requests must check for
legal-retention conflicts (e.g. RBI KYC/PMLA minimum retention) before being marked
fulfilled — this migration adds the tracking columns; the actual RBI-DPDP reconciliation
logic is wired in by a later migration/service (app.privacy.services.retention_conflict_service).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0296_dsr_grievance_retention_conflict_nomination"
down_revision: str | None = "0295_sdf_designation_suggestions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "data_subject_requests",
        sa.Column("request_subtype", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "data_subject_requests",
        sa.Column("data_categories", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "data_subject_requests",
        sa.Column("retention_conflict_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "data_subject_requests",
        sa.Column("retention_conflict_overridden_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "data_subject_requests",
        sa.Column("retention_conflict_override_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "data_subject_requests",
        sa.Column("submitted_by_nominee_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_dsr_submitted_by_nominee",
        "data_subject_requests",
        "data_principal_nominations",
        ["submitted_by_nominee_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_dsr_request_subtype",
        "data_subject_requests",
        "request_subtype IS NULL OR request_subtype IN ('rights_request', 'grievance')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_dsr_request_subtype", "data_subject_requests", type_="check")
    op.drop_constraint("fk_dsr_submitted_by_nominee", "data_subject_requests", type_="foreignkey")
    op.drop_column("data_subject_requests", "submitted_by_nominee_id")
    op.drop_column("data_subject_requests", "retention_conflict_override_reason")
    op.drop_column("data_subject_requests", "retention_conflict_overridden_at")
    op.drop_column("data_subject_requests", "retention_conflict_json")
    op.drop_column("data_subject_requests", "data_categories")
    op.drop_column("data_subject_requests", "request_subtype")
