"""add import_jobs and source_import_tool columns for m1 slice

Revision ID: 0246_import_jobs_m1
Revises: 0245_saml_replay
Create Date: 2026-07-06 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0246_import_jobs_m1"
down_revision: str | None = "0245_saml_replay"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "import_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("source_tool", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress_current", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("conflict_strategy", sa.String(length=16), nullable=False, server_default="skip"),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("raw_payload_json", sa.JSON(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "source_tool IN ('vanta', 'drata', 'sprinto', 'scrut', 'generic')",
            name="ck_import_jobs_source_tool",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'processing', 'preview_ready', 'completed', 'failed')",
            name="ck_import_jobs_status",
        ),
        sa.CheckConstraint(
            "conflict_strategy IN ('skip', 'update')",
            name="ck_import_jobs_conflict_strategy",
        ),
        sa.CheckConstraint("progress_current >= 0", name="ck_import_jobs_progress_current"),
        sa.CheckConstraint("progress_total >= 0", name="ck_import_jobs_progress_total"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_import_jobs_org_status", "import_jobs", ["organization_id", "status"], unique=False)
    op.create_index("ix_import_jobs_org_source", "import_jobs", ["organization_id", "source_tool"], unique=False)
    op.create_index("ix_import_jobs_created_at", "import_jobs", ["created_at"], unique=False)
    op.create_index(op.f("ix_import_jobs_organization_id"), "import_jobs", ["organization_id"], unique=False)

    op.add_column("evidence_items", sa.Column("source_import_tool", sa.String(length=32), nullable=True))
    op.add_column("controls", sa.Column("source_import_tool", sa.String(length=32), nullable=True))
    op.add_column("business_units", sa.Column("source_import_tool", sa.String(length=32), nullable=True))
    op.add_column("compliance_policies", sa.Column("source_import_tool", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("compliance_policies", "source_import_tool")
    op.drop_column("business_units", "source_import_tool")
    op.drop_column("controls", "source_import_tool")
    op.drop_column("evidence_items", "source_import_tool")

    op.drop_index(op.f("ix_import_jobs_organization_id"), table_name="import_jobs")
    op.drop_index("ix_import_jobs_created_at", table_name="import_jobs")
    op.drop_index("ix_import_jobs_org_source", table_name="import_jobs")
    op.drop_index("ix_import_jobs_org_status", table_name="import_jobs")
    op.drop_table("import_jobs")
