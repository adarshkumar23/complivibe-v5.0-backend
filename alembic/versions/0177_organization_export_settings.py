"""organization export settings

Revision ID: 0177_organization_export_settings
Revises: 0176_business_units_data_tagging
Create Date: 2026-06-30 11:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0177_organization_export_settings"
down_revision: str | None = "0176_business_units_data_tagging"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return inspector.has_table(table_name)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "organization_export_settings"):
        op.create_table(
            "organization_export_settings",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
            sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("logo_url", sa.VARCHAR(length=500), nullable=True),
            sa.Column("company_display_name", sa.VARCHAR(length=200), nullable=True),
            sa.Column("footer_text", sa.VARCHAR(length=500), nullable=True),
            sa.Column("primary_color_hex", sa.VARCHAR(length=7), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_org_exp_set_org", ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("organization_id", name="uq_org_exp_set_org"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_table(inspector, "organization_export_settings"):
        op.drop_table("organization_export_settings")
