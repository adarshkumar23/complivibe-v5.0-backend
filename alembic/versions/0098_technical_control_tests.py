"""automated technical control tests

Revision ID: 0098_technical_control_tests
Revises: 0097_oscal_export_jobs
Create Date: 2026-06-23 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0098_technical_control_tests"
down_revision: str | None = "0097_oscal_export_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "technical_control_agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_technical_control_agents_organization_id",
        "technical_control_agents",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_technical_control_agents_token_hash",
        "technical_control_agents",
        ["token_hash"],
        unique=False,
    )
    op.create_index(
        "uq_technical_control_agents_org_name_active",
        "technical_control_agents",
        ["organization_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "technical_control_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("control_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_resource_type", sa.String(length=100), nullable=False),
        sa.Column("expected_config_key", sa.String(length=255), nullable=False),
        sa.Column("expected_config_value", sa.Text(), nullable=False),
        sa.Column("evaluation_operator", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=20), server_default=sa.text("'warning'"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "target_resource_type IN ('aws_s3', 'aws_iam', 'aws_ec2', 'aws_rds', 'gcp_iam', 'gcp_storage', 'azure_ad', 'azure_storage', 'network', 'os', 'generic')",
            name="ck_technical_control_rules_target_resource_type",
        ),
        sa.CheckConstraint(
            "evaluation_operator IN ('equals', 'not_equals', 'contains', 'not_contains', 'gte', 'lte', 'is_true', 'is_false', 'exists', 'not_exists')",
            name="ck_technical_control_rules_evaluation_operator",
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="ck_technical_control_rules_severity",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["control_id"], ["controls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_technical_control_rules_organization_id",
        "technical_control_rules",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_technical_control_rules_org_control",
        "technical_control_rules",
        ["organization_id", "control_id"],
        unique=False,
    )
    op.create_index(
        "ix_technical_control_rules_org_active",
        "technical_control_rules",
        ["organization_id", "is_active"],
        unique=False,
    )

    op.create_table(
        "technical_control_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_identifier", sa.String(length=500), nullable=True),
        sa.Column("actual_config_key", sa.String(length=255), nullable=False),
        sa.Column("actual_config_value", sa.Text(), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("control_test_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_id"], ["technical_control_rules.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["agent_id"], ["technical_control_agents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["control_test_run_id"], ["control_test_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_technical_control_results_organization_id",
        "technical_control_results",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_technical_control_results_org_rule_created",
        "technical_control_results",
        ["organization_id", "rule_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_technical_control_results_org_agent_created",
        "technical_control_results",
        ["organization_id", "agent_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_technical_control_results_org_passed_created",
        "technical_control_results",
        ["organization_id", "passed", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_technical_control_results_org_passed_created", table_name="technical_control_results")
    op.drop_index("ix_technical_control_results_org_agent_created", table_name="technical_control_results")
    op.drop_index("ix_technical_control_results_org_rule_created", table_name="technical_control_results")
    op.drop_index("ix_technical_control_results_organization_id", table_name="technical_control_results")
    op.drop_table("technical_control_results")

    op.drop_index("ix_technical_control_rules_org_active", table_name="technical_control_rules")
    op.drop_index("ix_technical_control_rules_org_control", table_name="technical_control_rules")
    op.drop_index("ix_technical_control_rules_organization_id", table_name="technical_control_rules")
    op.drop_table("technical_control_rules")

    op.drop_index("uq_technical_control_agents_org_name_active", table_name="technical_control_agents")
    op.drop_index("ix_technical_control_agents_token_hash", table_name="technical_control_agents")
    op.drop_index("ix_technical_control_agents_organization_id", table_name="technical_control_agents")
    op.drop_table("technical_control_agents")
