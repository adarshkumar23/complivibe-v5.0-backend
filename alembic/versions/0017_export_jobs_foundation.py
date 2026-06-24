"""export jobs foundation

Revision ID: 0017_export_jobs_foundation
Revises: 0016_compliance_reporting_foundation
Create Date: 2026-06-18 23:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0017_export_jobs_foundation"
down_revision: Union[str, Sequence[str], None] = "0016_compliance_reporting_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "export_jobs",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("export_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("source_report_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("framework_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("package_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("manifest_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("provenance_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("checksum_sha256", sa.String(length=128), nullable=True),
        sa.Column("integrity_signature", sa.String(length=256), nullable=True),
        sa.Column("signing_key_id", sa.String(length=64), nullable=True),
        sa.Column("signature_algorithm", sa.String(length=64), nullable=True),
        sa.Column("package_version", sa.String(length=32), nullable=False, server_default="1.0"),
        sa.Column("immutable_after_completion", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_report_id"], ["compliance_reports.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["framework_id"], ["frameworks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_export_jobs_org_type", "export_jobs", ["organization_id", "export_type"], unique=False)
    op.create_index("ix_export_jobs_org_status", "export_jobs", ["organization_id", "status"], unique=False)
    op.create_index("ix_export_jobs_org_framework", "export_jobs", ["organization_id", "framework_id"], unique=False)
    op.create_index("ix_export_jobs_org_completed", "export_jobs", ["organization_id", "completed_at"], unique=False)

    op.create_table(
        "export_job_events",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("export_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=True),
        sa.Column("details_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["export_job_id"], ["export_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_export_job_events_org_job", "export_job_events", ["organization_id", "export_job_id"], unique=False)
    op.create_index("ix_export_job_events_job_created", "export_job_events", ["export_job_id", "created_at"], unique=False)
    op.create_index("ix_export_job_events_org_type", "export_job_events", ["organization_id", "event_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_export_job_events_org_type", table_name="export_job_events")
    op.drop_index("ix_export_job_events_job_created", table_name="export_job_events")
    op.drop_index("ix_export_job_events_org_job", table_name="export_job_events")
    op.drop_table("export_job_events")

    op.drop_index("ix_export_jobs_org_completed", table_name="export_jobs")
    op.drop_index("ix_export_jobs_org_framework", table_name="export_jobs")
    op.drop_index("ix_export_jobs_org_status", table_name="export_jobs")
    op.drop_index("ix_export_jobs_org_type", table_name="export_jobs")
    op.drop_table("export_jobs")
