"""add jira linear bidirectional issue sync structures

Revision ID: 0248_issue_sync_i3
Revises: 0247_compliance_bot_i2
Create Date: 2026-07-06
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0248_issue_sync_i3"
down_revision: str | None = "0247_compliance_bot_i2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "external_sync_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False, server_default=sa.text("'issue'")),
        sa.Column("direction_mode", sa.String(length=32), nullable=False, server_default=sa.text("'two_way'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("project_ref", sa.String(length=128), nullable=True),
        sa.Column("api_base_url", sa.Text(), nullable=True),
        sa.Column("credentials_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("webhook_secret", sa.String(length=255), nullable=True),
        sa.Column("field_mapping_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint("provider IN ('jira','linear')", name="ck_external_sync_connections_provider"),
        sa.CheckConstraint(
            "direction_mode IN ('outbound_only','inbound_only','two_way')",
            name="ck_external_sync_connections_direction",
        ),
        sa.CheckConstraint("entity_type IN ('issue')", name="ck_external_sync_connections_entity_type"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_external_sync_connections_org_provider",
        "external_sync_connections",
        ["organization_id", "provider"],
        unique=False,
    )
    op.create_index(
        "ix_external_sync_connections_org_active",
        "external_sync_connections",
        ["organization_id", "is_active"],
        unique=False,
    )

    op.create_table(
        "external_sync_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False, server_default=sa.text("'issue'")),
        sa.Column("internal_entity_id", sa.Uuid(), nullable=False),
        sa.Column("external_entity_id", sa.String(length=255), nullable=False),
        sa.Column("external_key", sa.String(length=255), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(length=64), nullable=True),
        sa.CheckConstraint("entity_type IN ('issue')", name="ck_external_sync_links_entity_type"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connection_id"], ["external_sync_connections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connection_id",
            "entity_type",
            "internal_entity_id",
            name="uq_external_sync_links_connection_internal",
        ),
        sa.UniqueConstraint(
            "connection_id",
            "entity_type",
            "external_entity_id",
            name="uq_external_sync_links_connection_external",
        ),
    )
    op.create_index(
        "ix_external_sync_links_org_connection",
        "external_sync_links",
        ["organization_id", "connection_id"],
        unique=False,
    )

    op.create_table(
        "external_sync_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False, server_default=sa.text("'issue'")),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("external_event_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'processed'")),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("provider IN ('jira','linear')", name="ck_external_sync_events_provider"),
        sa.CheckConstraint("direction IN ('inbound','outbound')", name="ck_external_sync_events_direction"),
        sa.CheckConstraint("entity_type IN ('issue')", name="ck_external_sync_events_entity_type"),
        sa.CheckConstraint("status IN ('processed','failed','ignored')", name="ck_external_sync_events_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connection_id"], ["external_sync_connections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_external_sync_events_org_connection",
        "external_sync_events",
        ["organization_id", "connection_id"],
        unique=False,
    )
    op.create_index(
        "ix_external_sync_events_org_provider",
        "external_sync_events",
        ["organization_id", "provider"],
        unique=False,
    )
    op.create_index(
        "ix_external_sync_events_processed_at",
        "external_sync_events",
        ["processed_at"],
        unique=False,
    )

    op.create_table(
        "issue_sync_comments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("issue_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("external_comment_id", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author_ref", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("provider IN ('internal','jira','linear')", name="ck_issue_sync_comments_provider"),
        sa.CheckConstraint("direction IN ('inbound','outbound')", name="ck_issue_sync_comments_direction"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_issue_sync_comments_org_issue",
        "issue_sync_comments",
        ["organization_id", "issue_id"],
        unique=False,
    )
    op.create_index(
        "ix_issue_sync_comments_org_provider",
        "issue_sync_comments",
        ["organization_id", "provider"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_issue_sync_comments_org_provider", table_name="issue_sync_comments")
    op.drop_index("ix_issue_sync_comments_org_issue", table_name="issue_sync_comments")
    op.drop_table("issue_sync_comments")
    op.drop_index("ix_external_sync_events_processed_at", table_name="external_sync_events")
    op.drop_index("ix_external_sync_events_org_provider", table_name="external_sync_events")
    op.drop_index("ix_external_sync_events_org_connection", table_name="external_sync_events")
    op.drop_table("external_sync_events")
    op.drop_index("ix_external_sync_links_org_connection", table_name="external_sync_links")
    op.drop_table("external_sync_links")
    op.drop_index("ix_external_sync_connections_org_active", table_name="external_sync_connections")
    op.drop_index("ix_external_sync_connections_org_provider", table_name="external_sync_connections")
    op.drop_table("external_sync_connections")
