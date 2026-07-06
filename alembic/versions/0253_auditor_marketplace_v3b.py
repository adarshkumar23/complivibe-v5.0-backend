"""add auditor marketplace and engagements

Revision ID: 0253_auditor_marketplace_v3b
Revises: 0252_certification_programs_v2b
Create Date: 2026-07-06 11:05:32.133616
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0253_auditor_marketplace_v3b"
down_revision: str | None = "0252_certification_programs_v2b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auditors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("firm", sa.String(length=255), nullable=False),
        sa.Column(
            "certifications_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "frameworks_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("rate_usd_per_day", sa.Numeric(12, 2), nullable=False),
        sa.Column("availability", sa.String(length=64), nullable=False, server_default="available"),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auditors_name", "auditors", ["name"], unique=False)
    op.create_index("ix_auditors_email", "auditors", ["email"], unique=True)
    op.create_index("ix_auditors_firm", "auditors", ["firm"], unique=False)
    op.create_index("ix_auditors_verified", "auditors", ["verified"], unique=False)
    op.create_index("ix_auditors_status", "auditors", ["status"], unique=False)

    op.create_table(
        "auditor_engagements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("auditor_id", sa.Uuid(), nullable=False),
        sa.Column("audit_engagement_id", sa.Uuid(), nullable=False),
        sa.Column("framework", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revenue_share_fee_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["auditor_id"], ["auditors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["audit_engagement_id"], ["audit_engagements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("revenue_share_fee_pct >= 10 AND revenue_share_fee_pct <= 15", name="ck_auditor_engagements_revenue_share_fee_pct"),
    )
    op.create_index("ix_auditor_engagements_org_status", "auditor_engagements", ["organization_id", "status"], unique=False)
    op.create_index("ix_auditor_engagements_org_auditor", "auditor_engagements", ["organization_id", "auditor_id"], unique=False)
    op.create_index("ix_auditor_engagements_org_started", "auditor_engagements", ["organization_id", "started_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_auditor_engagements_org_started", table_name="auditor_engagements")
    op.drop_index("ix_auditor_engagements_org_auditor", table_name="auditor_engagements")
    op.drop_index("ix_auditor_engagements_org_status", table_name="auditor_engagements")
    op.drop_table("auditor_engagements")

    op.drop_index("ix_auditors_status", table_name="auditors")
    op.drop_index("ix_auditors_verified", table_name="auditors")
    op.drop_index("ix_auditors_firm", table_name="auditors")
    op.drop_index("ix_auditors_email", table_name="auditors")
    op.drop_index("ix_auditors_name", table_name="auditors")
    op.drop_table("auditors")
