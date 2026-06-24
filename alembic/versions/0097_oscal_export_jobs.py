"""oscal export jobs

Revision ID: 0097_oscal_export_jobs
Revises: 0096_control_exceptions_and_common_controls
Create Date: 2026-06-23 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0097_oscal_export_jobs"
down_revision: str | None = "0096_control_exceptions_and_common_controls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oscal_export_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("export_type", sa.String(length=20), nullable=False),
        sa.Column("framework_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("oscal_version", sa.String(length=20), server_default=sa.text("'1.1.2'"), nullable=False),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result_size_bytes", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "export_type IN ('ssp', 'assessment_plan', 'assessment_results', 'full_package')",
            name="ck_oscal_export_jobs_export_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'complete', 'failed')",
            name="ck_oscal_export_jobs_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["framework_id"], ["frameworks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_oscal_export_jobs_organization_id", "oscal_export_jobs", ["organization_id"], unique=False)
    op.create_index(
        "ix_oscal_export_jobs_org_status",
        "oscal_export_jobs",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_oscal_export_jobs_org_type_created",
        "oscal_export_jobs",
        ["organization_id", "export_type", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_oscal_export_jobs_org_type_created", table_name="oscal_export_jobs")
    op.drop_index("ix_oscal_export_jobs_org_status", table_name="oscal_export_jobs")
    op.drop_index("ix_oscal_export_jobs_organization_id", table_name="oscal_export_jobs")
    op.drop_table("oscal_export_jobs")
