"""ai monitoring mode b inbound readings

Revision ID: 0129_ai_monitoring_mode_b
Revises: 0128_guardrails_and_approval_envelopes
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0129_ai_monitoring_mode_b"
down_revision: str | None = "0128_guardrails_and_approval_envelopes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_monitoring_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric_type", sa.String(length=50), nullable=False),
        sa.Column("threshold_value", sa.Numeric(10, 4), nullable=False),
        sa.Column("comparison_direction", sa.String(length=10), nullable=False),
        sa.Column("alert_on_breach", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("check_frequency", sa.String(length=20), nullable=True),
        sa.Column("baseline_value", sa.Numeric(10, 4), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reading_value", sa.Numeric(10, 4), nullable=True),
        sa.Column("api_key_hash", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "metric_type IN ('accuracy', 'bias_parity_gap', 'output_drift', 'confidence_distribution', 'response_time', 'error_rate')",
            name="ck_ai_monitoring_configs_metric_type",
        ),
        sa.CheckConstraint(
            "comparison_direction IN ('above', 'below')",
            name="ck_ai_monitoring_configs_comparison_direction",
        ),
        sa.CheckConstraint(
            "check_frequency IS NULL OR check_frequency IN ('realtime', 'hourly', 'daily', 'weekly')",
            name="ck_ai_monitoring_configs_check_frequency",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_monitoring_configs_org_system_active",
        "ai_monitoring_configs",
        ["organization_id", "ai_system_id", "is_active"],
        unique=False,
    )
    op.create_index(
        "ix_ai_monitoring_configs_org_metric",
        "ai_monitoring_configs",
        ["organization_id", "metric_type"],
        unique=False,
    )

    op.create_table(
        "ai_monitoring_readings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("config_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("value", sa.Numeric(10, 4), nullable=False),
        sa.Column("reading_source", sa.String(length=50), nullable=False),
        sa.Column("source_tool", sa.String(length=100), nullable=True),
        sa.Column("within_threshold", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "reading_source IN ('manual', 'api_report')",
            name="ck_ai_monitoring_readings_reading_source",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["config_id"], ["ai_monitoring_configs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_monitoring_readings_config_created",
        "ai_monitoring_readings",
        ["config_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_monitoring_readings_org_within",
        "ai_monitoring_readings",
        ["organization_id", "within_threshold"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_monitoring_readings_org_within", table_name="ai_monitoring_readings")
    op.drop_index("ix_ai_monitoring_readings_config_created", table_name="ai_monitoring_readings")
    op.drop_table("ai_monitoring_readings")

    op.drop_index("ix_ai_monitoring_configs_org_metric", table_name="ai_monitoring_configs")
    op.drop_index("ix_ai_monitoring_configs_org_system_active", table_name="ai_monitoring_configs")
    op.drop_table("ai_monitoring_configs")
