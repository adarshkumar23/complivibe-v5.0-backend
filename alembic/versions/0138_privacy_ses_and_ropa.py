"""privacy ses config and ropa tables

Revision ID: 0138_privacy_ses_and_ropa
Revises: 0137_obligation_links_and_residency
Create Date: 2026-06-26 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0138_privacy_ses_and_ropa"
down_revision: str | None = "0137_obligation_links_and_residency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "org_email_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False, server_default=sa.text("'ses'")),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("test_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("provider IN ('ses')", name="ck_org_email_configs_provider"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", name="uq_org_email_configs_org"),
    )

    op.create_table(
        "processing_activities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("legal_basis", sa.String(length=50), nullable=False),
        sa.Column("legitimate_interest_justification", sa.Text(), nullable=True),
        sa.Column("data_categories", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("special_categories", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("data_subject_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("retention_period", sa.String(length=255), nullable=True),
        sa.Column("retention_basis", sa.Text(), nullable=True),
        sa.Column("recipients", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("international_transfers", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("transfer_destinations", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("transfer_safeguards", sa.String(length=100), nullable=True),
        sa.Column("controller_name", sa.String(length=255), nullable=True),
        sa.Column("controller_contact", sa.String(length=255), nullable=True),
        sa.Column("dpo_contact", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("risk_level", sa.String(length=20), nullable=True),
        sa.Column("requires_dpia", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("linked_dpia_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("linked_data_asset_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("linked_subprocessor_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "legal_basis IN ('consent', 'contract', 'legal_obligation', 'vital_interests', 'public_task', 'legitimate_interests')",
            name="ck_processing_activities_legal_basis",
        ),
        sa.CheckConstraint("status IN ('active', 'under_review', 'suspended', 'discontinued')", name="ck_processing_activities_status"),
        sa.CheckConstraint("risk_level IS NULL OR risk_level IN ('low', 'medium', 'high', 'critical')", name="ck_processing_activities_risk_level"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_processing_activities_org_status", "processing_activities", ["organization_id", "status"], unique=False)
    op.create_index("ix_processing_activities_org_legal_basis", "processing_activities", ["organization_id", "legal_basis"], unique=False)
    op.create_index("ix_processing_activities_org_requires_dpia", "processing_activities", ["organization_id", "requires_dpia"], unique=False)
    op.create_index("ix_processing_activities_org_risk_level", "processing_activities", ["organization_id", "risk_level"], unique=False)

    op.create_table(
        "ropa_framework_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("processing_activity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("obligation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("linked_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["processing_activity_id"], ["processing_activities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["obligation_id"], ["obligations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["linked_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "processing_activity_id",
            "obligation_id",
            name="uq_ropa_framework_links_org_activity_obligation",
        ),
    )
    op.create_index("ix_ropa_framework_links_org_activity", "ropa_framework_links", ["organization_id", "processing_activity_id"], unique=False)
    op.create_index("ix_ropa_framework_links_org_obligation", "ropa_framework_links", ["organization_id", "obligation_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ropa_framework_links_org_obligation", table_name="ropa_framework_links")
    op.drop_index("ix_ropa_framework_links_org_activity", table_name="ropa_framework_links")
    op.drop_table("ropa_framework_links")

    op.drop_index("ix_processing_activities_org_risk_level", table_name="processing_activities")
    op.drop_index("ix_processing_activities_org_requires_dpia", table_name="processing_activities")
    op.drop_index("ix_processing_activities_org_legal_basis", table_name="processing_activities")
    op.drop_index("ix_processing_activities_org_status", table_name="processing_activities")
    op.drop_table("processing_activities")

    op.drop_table("org_email_configs")
