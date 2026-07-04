"""aml kyc checks

Revision ID: 0205_aml_kyc_checks
Revises: 0204_vendor_threat_intel
Create Date: 2026-07-04 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0205_aml_kyc_checks"
down_revision: str | None = "0204_vendor_threat_intel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "aml_kyc_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("signals_used", sa.JSON(), nullable=False),
        sa.Column("offshore_links_found", sa.JSON(), nullable=False),
        sa.Column("ubo_data", sa.JSON(), nullable=False),
        sa.Column("adverse_media_found", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_aml_kyc_checks_org_vendor", "aml_kyc_checks", ["organization_id", "vendor_id"], unique=False)
    op.create_index("ix_aml_kyc_checks_org_checked", "aml_kyc_checks", ["organization_id", "checked_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_aml_kyc_checks_org_checked", table_name="aml_kyc_checks")
    op.drop_index("ix_aml_kyc_checks_org_vendor", table_name="aml_kyc_checks")
    op.drop_table("aml_kyc_checks")
