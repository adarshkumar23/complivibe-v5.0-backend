"""add cloud evidence connectors (AWS/GCP/Azure/Okta/GitHub agent-push connectors)

Revision ID: 0298_cloud_evidence_connectors
Revises: 0297_rbi_dpdp_retention_anchor
Create Date: 2026-07-10 12:00:00.000000

Agent-push connector framework: CompliVibe never initiates an outbound scan/call against
a customer's cloud/IdP environment. Each connector instance exposes a webhook URL/token
that the customer's own provider-native push mechanism (EventBridge, Pub/Sub push
subscription, Event Grid, Event Hooks, GitHub webhooks) delivers findings to.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0298_cloud_evidence_connectors"
down_revision: str | None = "0297_rbi_dpdp_retention_anchor"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cloud_evidence_connectors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("connector_type", sa.String(length=20), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="unconfigured"),
        sa.Column("webhook_token", sa.String(length=64), nullable=False),
        sa.Column("signing_secret_ciphertext", sa.Text(), nullable=True),
        sa.Column("secret_revealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_config_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("auto_apply_deterministic_mappings", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("expected_event_interval_hours", sa.Integer(), nullable=False, server_default="24"),
        sa.Column("last_event_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("webhook_token", name="uq_cloud_connectors_webhook_token"),
        sa.CheckConstraint("connector_type IN ('aws', 'gcp', 'azure', 'okta', 'github')", name="ck_cloud_connectors_type"),
        sa.CheckConstraint("status IN ('unconfigured', 'active', 'disabled', 'error')", name="ck_cloud_connectors_status"),
    )
    op.create_index("ix_cloud_connectors_org_type", "cloud_evidence_connectors", ["organization_id", "connector_type"])
    op.create_index("ix_cloud_connectors_org_status", "cloud_evidence_connectors", ["organization_id", "status"])

    op.create_table(
        "cloud_evidence_connector_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("connector_id", sa.Uuid(), nullable=False),
        sa.Column("provider_event_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("evidence_item_id", sa.Uuid(), nullable=True),
        sa.Column("finding_summary_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connector_id"], ["cloud_evidence_connectors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_item_id"], ["evidence_items.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connector_id", "provider_event_id", name="uq_cloud_connector_events_dedup"),
        sa.CheckConstraint("status IN ('created', 'duplicate', 'error')", name="ck_cloud_connector_events_status"),
    )
    op.create_index("ix_cloud_connector_events_org_connector", "cloud_evidence_connector_events", ["organization_id", "connector_id"])

    op.create_table(
        "cloud_finding_control_mapping_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("finding_category", sa.String(length=100), nullable=False),
        sa.Column("target_control_id", sa.Uuid(), nullable=True),
        sa.Column("target_control_common_tag", sa.String(length=100), nullable=True),
        sa.Column("confidence", sa.String(length=32), nullable=False, server_default="deterministic_partial"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_control_id"], ["controls.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "confidence IN ('deterministic_exact', 'deterministic_partial', 'needs_review')",
            name="ck_cloud_finding_mapping_rules_confidence",
        ),
    )
    op.create_index(
        "ix_cloud_finding_mapping_rules_org_category", "cloud_finding_control_mapping_rules", ["organization_id", "finding_category"]
    )

    op.create_table(
        "finding_control_suggestions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("connector_event_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_item_id", sa.Uuid(), nullable=False),
        sa.Column("suggested_control_id", sa.Uuid(), nullable=False),
        sa.Column("confidence", sa.String(length=32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("applied_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissal_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connector_event_id"], ["cloud_evidence_connector_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_item_id"], ["evidence_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["suggested_control_id"], ["controls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["applied_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["dismissed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "confidence IN ('deterministic_exact', 'deterministic_partial', 'needs_review')",
            name="ck_finding_control_suggestions_confidence",
        ),
        sa.CheckConstraint("status IN ('open', 'applied', 'dismissed')", name="ck_finding_control_suggestions_status"),
    )
    op.create_index("ix_finding_control_suggestions_org_status", "finding_control_suggestions", ["organization_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_finding_control_suggestions_org_status", table_name="finding_control_suggestions")
    op.drop_table("finding_control_suggestions")
    op.drop_index("ix_cloud_finding_mapping_rules_org_category", table_name="cloud_finding_control_mapping_rules")
    op.drop_table("cloud_finding_control_mapping_rules")
    op.drop_index("ix_cloud_connector_events_org_connector", table_name="cloud_evidence_connector_events")
    op.drop_table("cloud_evidence_connector_events")
    op.drop_index("ix_cloud_connectors_org_status", table_name="cloud_evidence_connectors")
    op.drop_index("ix_cloud_connectors_org_type", table_name="cloud_evidence_connectors")
    op.drop_table("cloud_evidence_connectors")
