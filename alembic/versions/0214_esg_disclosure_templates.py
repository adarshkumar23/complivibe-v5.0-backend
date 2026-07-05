"""add esg disclosure template metadata

Revision ID: 0214_esg_disclosure_templates
Revises: 0213_sod_conflicts
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0214_esg_disclosure_templates"
down_revision: str | None = "0213_sod_conflicts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "custom_report_templates",
        sa.Column("template_type", sa.String(length=64), nullable=False, server_default="custom"),
    )
    op.add_column("custom_report_templates", sa.Column("system_template_key", sa.String(length=120), nullable=True))
    op.add_column("custom_report_templates", sa.Column("disclosure_structure", sa.JSON(), nullable=True))
    op.create_index("ix_custom_report_templates_org_type", "custom_report_templates", ["organization_id", "template_type"], unique=False)
    op.create_index(
        "uq_custom_report_templates_org_system_key_active",
        "custom_report_templates",
        ["organization_id", "system_template_key"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND system_template_key IS NOT NULL"),
        sqlite_where=sa.text("deleted_at IS NULL AND system_template_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_custom_report_templates_org_system_key_active", table_name="custom_report_templates")
    op.drop_index("ix_custom_report_templates_org_type", table_name="custom_report_templates")
    op.drop_column("custom_report_templates", "disclosure_structure")
    op.drop_column("custom_report_templates", "system_template_key")
    op.drop_column("custom_report_templates", "template_type")
