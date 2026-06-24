"""framework pack review and promotion workflow

Revision ID: 0025_framework_pack_review_promotion
Revises: 0024_framework_pack_coverage_reports
Create Date: 2026-06-18 15:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0025_framework_pack_review_promotion"
down_revision: str | None = "0024_framework_pack_coverage_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "framework_pack_review_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("framework_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("framework_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("pack_key", sa.String(length=128), nullable=True),
        sa.Column("coverage_report_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("review_type", sa.String(length=32), nullable=False),
        sa.Column("target_coverage_level", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("started_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("checklist_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("findings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("coverage_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("caveat", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["framework_id"], ["frameworks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["framework_version_id"], ["framework_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["coverage_report_id"], ["framework_pack_coverage_reports.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["started_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["completed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_framework_pack_review_runs_org_framework", "framework_pack_review_runs", ["organization_id", "framework_id"], unique=False)
    op.create_index("ix_framework_pack_review_runs_org_status", "framework_pack_review_runs", ["organization_id", "status"], unique=False)
    op.create_index("ix_framework_pack_review_runs_org_started_at", "framework_pack_review_runs", ["organization_id", "started_at"], unique=False)

    op.create_table(
        "framework_pack_review_signoffs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signer_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signer_role_name", sa.String(length=64), nullable=True),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signoff_checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("signoff_signature", sa.String(length=128), nullable=True),
        sa.Column("signing_key_id", sa.String(length=64), nullable=True),
        sa.Column("signature_algorithm", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["review_run_id"], ["framework_pack_review_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["signer_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("review_run_id", "signer_user_id", name="uq_framework_pack_review_signoff_signer"),
    )
    op.create_index("ix_framework_pack_review_signoffs_org_review", "framework_pack_review_signoffs", ["organization_id", "review_run_id"], unique=False)
    op.create_index("ix_framework_pack_review_signoffs_org_signed", "framework_pack_review_signoffs", ["organization_id", "signed_at"], unique=False)

    op.create_table(
        "framework_pack_promotion_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("framework_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("framework_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("review_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("from_coverage_level", sa.String(length=32), nullable=False),
        sa.Column("to_coverage_level", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("executed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["framework_id"], ["frameworks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["framework_version_id"], ["framework_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["review_run_id"], ["framework_pack_review_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["rejected_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["executed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_framework_pack_promotions_org_framework", "framework_pack_promotion_requests", ["organization_id", "framework_id"], unique=False)
    op.create_index("ix_framework_pack_promotions_org_status", "framework_pack_promotion_requests", ["organization_id", "status"], unique=False)
    op.create_index("ix_framework_pack_promotions_org_requested", "framework_pack_promotion_requests", ["organization_id", "requested_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_framework_pack_promotions_org_requested", table_name="framework_pack_promotion_requests")
    op.drop_index("ix_framework_pack_promotions_org_status", table_name="framework_pack_promotion_requests")
    op.drop_index("ix_framework_pack_promotions_org_framework", table_name="framework_pack_promotion_requests")
    op.drop_table("framework_pack_promotion_requests")

    op.drop_index("ix_framework_pack_review_signoffs_org_signed", table_name="framework_pack_review_signoffs")
    op.drop_index("ix_framework_pack_review_signoffs_org_review", table_name="framework_pack_review_signoffs")
    op.drop_table("framework_pack_review_signoffs")

    op.drop_index("ix_framework_pack_review_runs_org_started_at", table_name="framework_pack_review_runs")
    op.drop_index("ix_framework_pack_review_runs_org_status", table_name="framework_pack_review_runs")
    op.drop_index("ix_framework_pack_review_runs_org_framework", table_name="framework_pack_review_runs")
    op.drop_table("framework_pack_review_runs")
