"""data lineage tracking and data quality metrics

Revision ID: 0134_data_lineage_and_quality
Revises: 0133_data_assets_catalog_and_classification
Create Date: 2026-06-26 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0134_data_lineage_and_quality"
down_revision: str | None = "0133_data_assets_catalog_and_classification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_lineage_nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("node_type", sa.String(length=50), nullable=False),
        sa.Column("data_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("system_name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "node_type IN ('data_asset', 'transform', 'external_source', 'external_destination', 'api_endpoint', 'pipeline_step')",
            name="ck_data_lineage_nodes_node_type",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["data_asset_id"], ["data_assets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", "system_name", name="uq_data_lineage_nodes_org_name_system"),
    )
    op.create_index("ix_data_lineage_nodes_org_node_type", "data_lineage_nodes", ["organization_id", "node_type"], unique=False)
    op.create_index("ix_data_lineage_nodes_org_data_asset", "data_lineage_nodes", ["organization_id", "data_asset_id"], unique=False)

    op.create_table(
        "data_lineage_edges",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("upstream_node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("downstream_node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transformation_description", sa.Text(), nullable=True),
        sa.Column("source_method", sa.String(length=30), nullable=False),
        sa.Column("pipeline_name", sa.String(length=255), nullable=True),
        sa.Column("pipeline_run_id", sa.String(length=255), nullable=True),
        sa.Column("job_name", sa.String(length=255), nullable=True),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "source_method IN ('manual', 'openlineage_event', 'openmetadata_sync')",
            name="ck_data_lineage_edges_source_method",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["upstream_node_id"], ["data_lineage_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["downstream_node_id"], ["data_lineage_nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "upstream_node_id",
            "downstream_node_id",
            "pipeline_name",
            name="uq_data_lineage_edges_org_up_down_pipeline",
        ),
    )
    op.create_index("ix_data_lineage_edges_org_upstream", "data_lineage_edges", ["organization_id", "upstream_node_id"], unique=False)
    op.create_index(
        "ix_data_lineage_edges_org_downstream",
        "data_lineage_edges",
        ["organization_id", "downstream_node_id"],
        unique=False,
    )
    op.create_index("ix_data_lineage_edges_org_source_method", "data_lineage_edges", ["organization_id", "source_method"], unique=False)
    op.create_index("ix_data_lineage_edges_event_time", "data_lineage_edges", ["event_time"], unique=False)

    op.create_table(
        "openmetadata_integrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_status", sa.String(length=20), nullable=True),
        sa.Column("last_sync_error", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "sync_status IS NULL OR sync_status IN ('success', 'failed', 'in_progress')",
            name="ck_openmetadata_integrations_sync_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", name="uq_openmetadata_integrations_org"),
    )

    op.create_table(
        "data_quality_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("data_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric_type", sa.String(length=50), nullable=False),
        sa.Column("threshold_value", sa.Numeric(10, 4), nullable=False),
        sa.Column("comparison_direction", sa.String(length=10), nullable=False),
        sa.Column("alert_on_breach", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("measurement_frequency", sa.String(length=20), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_value", sa.Numeric(10, 4), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "metric_type IN ('completeness', 'accuracy', 'freshness', 'consistency', 'uniqueness')",
            name="ck_data_quality_configs_metric_type",
        ),
        sa.CheckConstraint(
            "comparison_direction IN ('above', 'below')",
            name="ck_data_quality_configs_comparison_direction",
        ),
        sa.CheckConstraint(
            "measurement_frequency IS NULL OR measurement_frequency IN ('realtime', 'hourly', 'daily', 'weekly')",
            name="ck_data_quality_configs_measurement_frequency",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["data_asset_id"], ["data_assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_data_quality_configs_org_asset_active",
        "data_quality_configs",
        ["organization_id", "data_asset_id", "is_active"],
        unique=False,
    )
    op.create_index("ix_data_quality_configs_org_metric", "data_quality_configs", ["organization_id", "metric_type"], unique=False)

    op.create_table(
        "data_quality_readings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("config_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("value", sa.Numeric(10, 4), nullable=False),
        sa.Column("reading_source", sa.String(length=30), nullable=False),
        sa.Column("source_tool", sa.String(length=100), nullable=True),
        sa.Column("within_threshold", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "reading_source IN ('manual', 'api_report')",
            name="ck_data_quality_readings_reading_source",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["config_id"], ["data_quality_configs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_data_quality_readings_config_created", "data_quality_readings", ["config_id", "created_at"], unique=False)
    op.create_index(
        "ix_data_quality_readings_org_within",
        "data_quality_readings",
        ["organization_id", "within_threshold"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_data_quality_readings_org_within", table_name="data_quality_readings")
    op.drop_index("ix_data_quality_readings_config_created", table_name="data_quality_readings")
    op.drop_table("data_quality_readings")

    op.drop_index("ix_data_quality_configs_org_metric", table_name="data_quality_configs")
    op.drop_index("ix_data_quality_configs_org_asset_active", table_name="data_quality_configs")
    op.drop_table("data_quality_configs")

    op.drop_table("openmetadata_integrations")

    op.drop_index("ix_data_lineage_edges_event_time", table_name="data_lineage_edges")
    op.drop_index("ix_data_lineage_edges_org_source_method", table_name="data_lineage_edges")
    op.drop_index("ix_data_lineage_edges_org_downstream", table_name="data_lineage_edges")
    op.drop_index("ix_data_lineage_edges_org_upstream", table_name="data_lineage_edges")
    op.drop_table("data_lineage_edges")

    op.drop_index("ix_data_lineage_nodes_org_data_asset", table_name="data_lineage_nodes")
    op.drop_index("ix_data_lineage_nodes_org_node_type", table_name="data_lineage_nodes")
    op.drop_table("data_lineage_nodes")
