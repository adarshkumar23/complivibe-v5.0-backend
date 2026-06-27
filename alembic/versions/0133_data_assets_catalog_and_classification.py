"""data asset catalog and classification

Revision ID: 0133_data_assets_catalog_and_classification
Revises: 0132_data_observability_scaffold
Create Date: 2026-06-26 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0133_data_assets_catalog_and_classification"
down_revision: str | None = "0132_data_observability_scaffold"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("asset_type", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("custodian_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sensitivity_tier", sa.String(length=20), nullable=True),
        sa.Column("classification_type", sa.String(length=50), nullable=True),
        sa.Column("classification_confidence", sa.Numeric(4, 2), nullable=True),
        sa.Column("classification_source", sa.String(length=20), nullable=True),
        sa.Column("classification_confirmed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("geographic_locations", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("permitted_regions", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("schema_column_names", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("retention_policy_days", sa.Integer(), nullable=True),
        sa.Column("retention_review_date", sa.Date(), nullable=True),
        sa.Column("data_volume_estimate", sa.String(length=100), nullable=True),
        sa.Column("source_system", sa.String(length=255), nullable=True),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "asset_type IN ('database', 'file_store', 'data_stream', 'api', 'data_lake', 'table', 'schema', 'bucket', 'other')",
            name="ck_data_assets_asset_type",
        ),
        sa.CheckConstraint(
            "sensitivity_tier IS NULL OR sensitivity_tier IN ('public', 'internal', 'confidential', 'restricted', 'secret')",
            name="ck_data_assets_sensitivity_tier",
        ),
        sa.CheckConstraint(
            "classification_type IS NULL OR classification_type IN ('personal_data', 'sensitive_personal_data', 'financial_data', 'health_data', 'intellectual_property', 'operational_data', 'public_data', 'unclassified')",
            name="ck_data_assets_classification_type",
        ),
        sa.CheckConstraint(
            "classification_source IS NULL OR classification_source IN ('metadata_rules', 'presidio_sample', 'manual')",
            name="ck_data_assets_classification_source",
        ),
        sa.CheckConstraint(
            "classification_confidence IS NULL OR (classification_confidence >= 0 AND classification_confidence <= 1)",
            name="ck_data_assets_classification_confidence",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'archived', 'under_review', 'decommissioned')",
            name="ck_data_assets_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["custodian_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_data_assets_org_asset_type", "data_assets", ["organization_id", "asset_type"], unique=False)
    op.create_index("ix_data_assets_org_sensitivity", "data_assets", ["organization_id", "sensitivity_tier"], unique=False)
    op.create_index("ix_data_assets_org_classification_type", "data_assets", ["organization_id", "classification_type"], unique=False)
    op.create_index("ix_data_assets_org_status", "data_assets", ["organization_id", "status"], unique=False)
    op.create_index(
        "ix_data_assets_org_classification_confirmed",
        "data_assets",
        ["organization_id", "classification_confirmed"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_data_assets_org_classification_confirmed", table_name="data_assets")
    op.drop_index("ix_data_assets_org_status", table_name="data_assets")
    op.drop_index("ix_data_assets_org_classification_type", table_name="data_assets")
    op.drop_index("ix_data_assets_org_sensitivity", table_name="data_assets")
    op.drop_index("ix_data_assets_org_asset_type", table_name="data_assets")
    op.drop_table("data_assets")
