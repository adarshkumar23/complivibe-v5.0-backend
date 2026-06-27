"""data access monitoring and retention policy enforcement

Revision ID: 0135_data_access_and_retention
Revises: 0134_data_lineage_and_quality
Create Date: 2026-06-26 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0135_data_access_and_retention"
down_revision: str | None = "0134_data_lineage_and_quality"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_access_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("data_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_external", sa.String(length=255), nullable=True),
        sa.Column("access_type", sa.String(length=20), nullable=False),
        sa.Column("access_result", sa.String(length=10), nullable=False),
        sa.Column("source_ip", sa.String(length=45), nullable=True),
        sa.Column("source_country", sa.String(length=2), nullable=True),
        sa.Column("bytes_transferred", sa.BigInteger(), nullable=True),
        sa.Column("row_count", sa.BigInteger(), nullable=True),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("access_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint("access_type IN ('read', 'write', 'delete', 'export', 'query')", name="ck_data_access_logs_access_type"),
        sa.CheckConstraint("access_result IN ('success', 'failed', 'partial')", name="ck_data_access_logs_access_result"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["data_asset_id"], ["data_assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_data_access_logs_org_asset_time", "data_access_logs", ["organization_id", "data_asset_id", "access_time"], unique=False)
    op.create_index("ix_data_access_logs_org_actor_time", "data_access_logs", ["organization_id", "actor_id", "access_time"], unique=False)
    op.create_index("ix_data_access_logs_org_result", "data_access_logs", ["organization_id", "access_result"], unique=False)
    op.create_index("ix_data_access_logs_access_time", "data_access_logs", ["access_time"], unique=False)
    op.create_index("ix_data_access_logs_source_country", "data_access_logs", ["source_country"], unique=False)

    op.create_table(
        "data_access_anomaly_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("data_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rule_type", sa.String(length=50), nullable=False),
        sa.Column("rule_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "rule_type IN ('access_count_spike', 'after_hours_access', 'new_actor_access', 'mass_download', 'failed_access_spike', 'cross_border_access', 'sensitivity_mismatch_access')",
            name="ck_data_access_anomaly_rules_rule_type",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["data_asset_id"], ["data_assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_data_access_anomaly_rules_org_type_active", "data_access_anomaly_rules", ["organization_id", "rule_type", "is_active"], unique=False)
    op.create_index("ix_data_access_anomaly_rules_org_asset_active", "data_access_anomaly_rules", ["organization_id", "data_asset_id", "is_active"], unique=False)

    op.create_table(
        "data_retention_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("max_retention_days", sa.Integer(), nullable=True),
        sa.Column("applies_to_classification_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("applies_to_sensitivity_tiers", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("legal_basis", sa.Text(), nullable=True),
        sa.Column("action_on_expiry", sa.String(length=20), nullable=False, server_default=sa.text("'flag'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("action_on_expiry IN ('flag', 'archive', 'delete')", name="ck_data_retention_policies_action_on_expiry"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_data_retention_policies_org_active", "data_retention_policies", ["organization_id", "is_active"], unique=False)

    op.create_table(
        "data_retention_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("data_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("review_type", sa.String(length=20), nullable=False),
        sa.Column("days_overdue", sa.Integer(), nullable=True),
        sa.Column("required_action", sa.String(length=20), nullable=False),
        sa.Column("linked_task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('pending', 'in_review', 'completed', 'waived')", name="ck_data_retention_reviews_status"),
        sa.CheckConstraint(
            "review_type IN ('retention_expired', 'max_retention_exceeded', 'manual_review')",
            name="ck_data_retention_reviews_review_type",
        ),
        sa.CheckConstraint("required_action IN ('flag', 'archive', 'delete')", name="ck_data_retention_reviews_required_action"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["data_asset_id"], ["data_assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_id"], ["data_retention_policies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_data_retention_reviews_org_status", "data_retention_reviews", ["organization_id", "status"], unique=False)
    op.create_index("ix_data_retention_reviews_org_asset", "data_retention_reviews", ["organization_id", "data_asset_id"], unique=False)
    op.create_index("ix_data_retention_reviews_created", "data_retention_reviews", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_data_retention_reviews_created", table_name="data_retention_reviews")
    op.drop_index("ix_data_retention_reviews_org_asset", table_name="data_retention_reviews")
    op.drop_index("ix_data_retention_reviews_org_status", table_name="data_retention_reviews")
    op.drop_table("data_retention_reviews")

    op.drop_index("ix_data_retention_policies_org_active", table_name="data_retention_policies")
    op.drop_table("data_retention_policies")

    op.drop_index("ix_data_access_anomaly_rules_org_asset_active", table_name="data_access_anomaly_rules")
    op.drop_index("ix_data_access_anomaly_rules_org_type_active", table_name="data_access_anomaly_rules")
    op.drop_table("data_access_anomaly_rules")

    op.drop_index("ix_data_access_logs_source_country", table_name="data_access_logs")
    op.drop_index("ix_data_access_logs_access_time", table_name="data_access_logs")
    op.drop_index("ix_data_access_logs_org_result", table_name="data_access_logs")
    op.drop_index("ix_data_access_logs_org_actor_time", table_name="data_access_logs")
    op.drop_index("ix_data_access_logs_org_asset_time", table_name="data_access_logs")
    op.drop_table("data_access_logs")
