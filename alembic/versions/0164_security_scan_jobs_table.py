"""security scan jobs table

Revision ID: 0164_security_scan_jobs_table
Revises: 0163_scim_tokens_table
Create Date: 2026-06-28 17:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0164_security_scan_jobs_table"
down_revision: str | None = "0163_scim_tokens_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("security_scan_jobs"):
        return

    op.create_table(
        "security_scan_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scan_source", sa.VARCHAR(length=30), nullable=False),
        sa.Column("scan_type", sa.VARCHAR(length=50), nullable=False),
        sa.Column("status", sa.VARCHAR(length=20), nullable=False, server_default=sa.text("'received'")),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_findings", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("critical_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("high_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("medium_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("low_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("issues_created", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("control_tests_created", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("source_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "scan_source IN ('trivy', 'prowler', 'openscap', 'wazuh', 'custom')",
            name="ck_security_scan_jobs_scan_source",
        ),
        sa.CheckConstraint(
            "scan_type IN ('container_image', 'infrastructure', 'compliance', 'siem_alert', 'custom')",
            name="ck_security_scan_jobs_scan_type",
        ),
        sa.CheckConstraint(
            "status IN ('received', 'processing', 'completed', 'failed')",
            name="ck_security_scan_jobs_status",
        ),
    )
    op.create_index("ix_security_scan_jobs_org_source", "security_scan_jobs", ["organization_id", "scan_source"], unique=False)
    op.create_index("ix_security_scan_jobs_org_status", "security_scan_jobs", ["organization_id", "status"], unique=False)
    op.create_index("ix_security_scan_jobs_submitted_at", "security_scan_jobs", ["submitted_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("security_scan_jobs"):
        op.drop_index("ix_security_scan_jobs_submitted_at", table_name="security_scan_jobs")
        op.drop_index("ix_security_scan_jobs_org_status", table_name="security_scan_jobs")
        op.drop_index("ix_security_scan_jobs_org_source", table_name="security_scan_jobs")
        op.drop_table("security_scan_jobs")
