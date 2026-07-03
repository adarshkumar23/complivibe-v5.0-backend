"""siem export config

Revision ID: 0168_siem_export_config
Revises: 0167_rate_limit_configs
Create Date: 2026-06-28 23:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0168_siem_export_config"
down_revision: str | None = "0167_rate_limit_configs"
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

    if not _has_table(inspector, "siem_export_configs"):
        op.create_table(
            "siem_export_configs",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("export_format", sa.VARCHAR(length=20), nullable=False, server_default=sa.text("'json'")),
            sa.Column("delivery_method", sa.VARCHAR(length=20), nullable=False, server_default=sa.text("'webhook'")),
            sa.Column("endpoint_url", sa.Text(), nullable=True),
            sa.Column("api_key_hash", sa.VARCHAR(length=64), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("include_actions", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
            sa.Column("exclude_actions", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
            sa.Column("batch_size", sa.Integer(), nullable=False, server_default=sa.text("100")),
            sa.Column("last_exported_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_export_id", sa.Uuid(), nullable=True),
            sa.Column("export_failures", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "export_format IN ('json', 'cef', 'leef', 'splunk_hec')",
                name="ck_siem_export_configs_format",
            ),
            sa.CheckConstraint(
                "delivery_method IN ('webhook', 'syslog', 'file', 'api_pull')",
                name="ck_siem_export_configs_delivery_method",
            ),
        )

    inspector = sa.inspect(bind)
    if not _has_index(inspector, "siem_export_configs", "ix_siem_export_configs_org_active"):
        op.create_index(
            "ix_siem_export_configs_org_active",
            "siem_export_configs",
            ["organization_id", "is_active"],
            unique=False,
        )

    inspector = sa.inspect(bind)
    if not _has_table(inspector, "siem_export_runs"):
        op.create_table(
            "siem_export_runs",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("config_id", sa.Uuid(), sa.ForeignKey("siem_export_configs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("status", sa.VARCHAR(length=20), nullable=False, server_default=sa.text("'running'")),
            sa.Column("records_exported", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("cursor_start", sa.Uuid(), nullable=True),
            sa.Column("cursor_end", sa.Uuid(), nullable=True),
            sa.CheckConstraint(
                "status IN ('running', 'completed', 'failed', 'partial')",
                name="ck_siem_export_runs_status",
            ),
        )

    inspector = sa.inspect(bind)
    if not _has_index(inspector, "siem_export_runs", "ix_siem_export_runs_org_config"):
        op.create_index(
            "ix_siem_export_runs_org_config",
            "siem_export_runs",
            ["organization_id", "config_id"],
            unique=False,
        )
    if not _has_index(inspector, "siem_export_runs", "ix_siem_export_runs_started_at"):
        op.create_index(
            "ix_siem_export_runs_started_at",
            "siem_export_runs",
            ["started_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "siem_export_runs"):
        if _has_index(inspector, "siem_export_runs", "ix_siem_export_runs_started_at"):
            op.drop_index("ix_siem_export_runs_started_at", table_name="siem_export_runs")
        if _has_index(inspector, "siem_export_runs", "ix_siem_export_runs_org_config"):
            op.drop_index("ix_siem_export_runs_org_config", table_name="siem_export_runs")
        op.drop_table("siem_export_runs")

    inspector = sa.inspect(bind)
    if _has_table(inspector, "siem_export_configs"):
        if _has_index(inspector, "siem_export_configs", "ix_siem_export_configs_org_active"):
            op.drop_index("ix_siem_export_configs_org_active", table_name="siem_export_configs")
        op.drop_table("siem_export_configs")
