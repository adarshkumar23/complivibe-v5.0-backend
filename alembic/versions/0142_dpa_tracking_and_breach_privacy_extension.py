"""dpa tracking and breach privacy extension

Revision ID: 0142_dpa_tracking_and_breach_privacy_extension
Revises: 0141_dpia_and_lawful_basis
Create Date: 2026-06-26 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0142_dpa_tracking_and_breach_privacy_extension"
down_revision: str | None = "0141_dpia_and_lawful_basis"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dpa_agreements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("counterparty_name", sa.String(length=255), nullable=False),
        sa.Column("counterparty_type", sa.String(length=20), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("subprocessor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dpa_reference", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("signed_date", sa.Date(), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("auto_renews", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("renewal_notice_days", sa.Integer(), nullable=False, server_default=sa.text("30")),
        sa.Column("governing_regulation", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("article28_compliant", sa.Boolean(), nullable=True),
        sa.Column("sccs_included", sa.Boolean(), nullable=True),
        sa.Column("bcrs_included", sa.Boolean(), nullable=True),
        sa.Column("data_transfer_countries", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("processing_activity_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "counterparty_type IN ('processor', 'sub_processor', 'joint_controller', 'controller')",
            name="ck_dpa_agreements_counterparty_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'expired', 'under_review', 'terminated')",
            name="ck_dpa_agreements_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dpa_agreements_org_status", "dpa_agreements", ["organization_id", "status"], unique=False)
    op.create_index("ix_dpa_agreements_org_counterparty_type", "dpa_agreements", ["organization_id", "counterparty_type"], unique=False)
    op.create_index("ix_dpa_agreements_expiry_status", "dpa_agreements", ["expiry_date", "status"], unique=False)
    op.create_index("ix_dpa_agreements_org_vendor", "dpa_agreements", ["organization_id", "vendor_id"], unique=False)
    op.create_index("ix_dpa_agreements_org_subprocessor", "dpa_agreements", ["organization_id", "subprocessor_id"], unique=False)

    op.add_column("breach_notifications", sa.Column("data_subjects_affected_count", sa.Integer(), nullable=True))
    op.add_column(
        "breach_notifications",
        sa.Column("special_category_data_involved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("breach_notifications", sa.Column("article33_notification_text", sa.Text(), nullable=True))
    op.add_column(
        "breach_notifications",
        sa.Column("article34_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("breach_notifications", sa.Column("subjects_notification_text", sa.Text(), nullable=True))
    op.add_column("breach_notifications", sa.Column("dpa_reference_number", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("breach_notifications", "dpa_reference_number")
    op.drop_column("breach_notifications", "subjects_notification_text")
    op.drop_column("breach_notifications", "article34_required")
    op.drop_column("breach_notifications", "article33_notification_text")
    op.drop_column("breach_notifications", "special_category_data_involved")
    op.drop_column("breach_notifications", "data_subjects_affected_count")

    op.drop_index("ix_dpa_agreements_org_subprocessor", table_name="dpa_agreements")
    op.drop_index("ix_dpa_agreements_org_vendor", table_name="dpa_agreements")
    op.drop_index("ix_dpa_agreements_expiry_status", table_name="dpa_agreements")
    op.drop_index("ix_dpa_agreements_org_counterparty_type", table_name="dpa_agreements")
    op.drop_index("ix_dpa_agreements_org_status", table_name="dpa_agreements")
    op.drop_table("dpa_agreements")
