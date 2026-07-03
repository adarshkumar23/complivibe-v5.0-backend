"""rate limit configs

Revision ID: 0167_rate_limit_configs
Revises: 0166_data_assets_import_fields
Create Date: 2026-06-28 22:30:00.000000
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import insert

revision: str = "0167_rate_limit_configs"
down_revision: str | None = "0166_data_assets_import_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DEFAULT_ROWS: list[tuple[str, int, int, int | None, int]] = [
    ("api_general", 60, 1000, 10000, 10),
    ("ingest", 30, 500, 5000, 10),
    ("auth", 10, 100, 500, 10),
    ("reports", 20, 200, 2000, 10),
    ("public", 120, 2000, None, 10),
    ("ai_governance", 30, 500, 5000, 10),
    ("scim", 60, 1000, None, 10),
]


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return inspector.has_table(table_name)


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return any(item.get("name") == index_name for item in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "rate_limit_configs"):
        op.create_table(
            "rate_limit_configs",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True),
            sa.Column("endpoint_group", sa.VARCHAR(length=50), nullable=False),
            sa.Column("requests_per_minute", sa.Integer(), nullable=False),
            sa.Column("requests_per_hour", sa.Integer(), nullable=False),
            sa.Column("requests_per_day", sa.Integer(), nullable=True),
            sa.Column("burst_allowance", sa.Integer(), nullable=False, server_default=sa.text("10")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint(
                "endpoint_group IN ('api_general', 'ingest', 'auth', 'reports', 'public', 'ai_governance', 'scim')",
                name="ck_rate_limit_configs_endpoint_group",
            ),
            sa.UniqueConstraint("organization_id", "endpoint_group", name="uq_rate_limit_configs_org_group"),
        )

    inspector = sa.inspect(bind)
    if not _has_index(inspector, "rate_limit_configs", "ix_rate_limit_configs_org_group_active"):
        op.create_index(
            "ix_rate_limit_configs_org_group_active",
            "rate_limit_configs",
            ["organization_id", "endpoint_group", "is_active"],
            unique=False,
        )

    inspector = sa.inspect(bind)
    if not _has_index(inspector, "rate_limit_configs", "uix_rate_limit_configs_platform_group"):
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uix_rate_limit_configs_platform_group
            ON rate_limit_configs(endpoint_group)
            WHERE organization_id IS NULL;
            """
        )

    table = sa.table(
        "rate_limit_configs",
        sa.column("id", sa.Uuid()),
        sa.column("organization_id", sa.Uuid()),
        sa.column("endpoint_group", sa.String()),
        sa.column("requests_per_minute", sa.Integer()),
        sa.column("requests_per_hour", sa.Integer()),
        sa.column("requests_per_day", sa.Integer()),
        sa.column("burst_allowance", sa.Integer()),
        sa.column("is_active", sa.Boolean()),
    )

    for endpoint_group, rpm, rph, rpd, burst in DEFAULT_ROWS:
        stmt = insert(table).values(
            id=uuid.uuid4(),
            organization_id=None,
            endpoint_group=endpoint_group,
            requests_per_minute=rpm,
            requests_per_hour=rph,
            requests_per_day=rpd,
            burst_allowance=burst,
            is_active=True,
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=["endpoint_group"], index_where=sa.text("organization_id IS NULL"))
        bind.execute(stmt)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "rate_limit_configs"):
        if _has_index(inspector, "rate_limit_configs", "uix_rate_limit_configs_platform_group"):
            op.drop_index("uix_rate_limit_configs_platform_group", table_name="rate_limit_configs")
        if _has_index(inspector, "rate_limit_configs", "ix_rate_limit_configs_org_group_active"):
            op.drop_index("ix_rate_limit_configs_org_group_active", table_name="rate_limit_configs")
        op.drop_table("rate_limit_configs")
