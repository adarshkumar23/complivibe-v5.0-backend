"""secure report sharing

Revision ID: 0169_secure_report_sharing
Revises: 0168_siem_export_config
Create Date: 2026-06-28 23:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0169_secure_report_sharing"
down_revision: str | None = "0168_siem_export_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return inspector.has_table(table_name)


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(item.get("name") == index_name for item in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "shared_report_links"):
        op.create_table(
            "shared_report_links",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("report_type", sa.VARCHAR(length=50), nullable=False),
            sa.Column("report_params", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("token", sa.VARCHAR(length=128), nullable=False, unique=True),
            sa.Column("password_hash", sa.VARCHAR(length=64), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("max_views", sa.Integer(), nullable=True),
            sa.Column("view_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("recipient_email", sa.VARCHAR(length=255), nullable=True),
            sa.Column("watermark_text", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        )

    inspector = sa.inspect(bind)
    if not _has_index(inspector, "shared_report_links", "ix_shared_report_links_token"):
        op.create_index("ix_shared_report_links_token", "shared_report_links", ["token"], unique=False)
    if not _has_index(inspector, "shared_report_links", "ix_shared_report_links_org_creator"):
        op.create_index(
            "ix_shared_report_links_org_creator",
            "shared_report_links",
            ["organization_id", "created_by"],
            unique=False,
        )
    if not _has_index(inspector, "shared_report_links", "ix_shared_report_links_exp_active"):
        op.create_index(
            "ix_shared_report_links_exp_active",
            "shared_report_links",
            ["expires_at", "is_active"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "shared_report_links"):
        if _has_index(inspector, "shared_report_links", "ix_shared_report_links_exp_active"):
            op.drop_index("ix_shared_report_links_exp_active", table_name="shared_report_links")
        if _has_index(inspector, "shared_report_links", "ix_shared_report_links_org_creator"):
            op.drop_index("ix_shared_report_links_org_creator", table_name="shared_report_links")
        if _has_index(inspector, "shared_report_links", "ix_shared_report_links_token"):
            op.drop_index("ix_shared_report_links_token", table_name="shared_report_links")
        op.drop_table("shared_report_links")
