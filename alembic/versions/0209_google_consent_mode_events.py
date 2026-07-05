"""add google consent mode events

Revision ID: 0209_google_consent_mode_events
Revises: 0208_add_webhook_delivery_delivered_at
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0209_google_consent_mode_events"
down_revision: str | None = "0208_add_webhook_delivery_delivered_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "google_consent_mode_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("subject_identifier_hash", sa.String(length=64), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("region", sa.String(length=50), nullable=True),
        sa.Column("client_id", sa.String(length=255), nullable=True),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("gcm_version", sa.String(length=20), nullable=False, server_default="v2"),
        sa.Column("event_name", sa.String(length=100), nullable=False, server_default="consent_update"),
        sa.Column("event_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ad_storage", sa.String(length=20), nullable=False),
        sa.Column("analytics_storage", sa.String(length=20), nullable=False),
        sa.Column("ad_user_data", sa.String(length=20), nullable=False),
        sa.Column("ad_personalization", sa.String(length=20), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("ad_personalization IN ('granted', 'denied')", name="ck_gcm_ad_personalization"),
        sa.CheckConstraint("ad_storage IN ('granted', 'denied')", name="ck_gcm_ad_storage"),
        sa.CheckConstraint("ad_user_data IN ('granted', 'denied')", name="ck_gcm_ad_user_data"),
        sa.CheckConstraint("analytics_storage IN ('granted', 'denied')", name="ck_gcm_analytics_storage"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_google_consent_mode_events_organization_id", "google_consent_mode_events", ["organization_id"], unique=False)
    op.create_index("ix_gcm_events_org_created", "google_consent_mode_events", ["organization_id", "created_at"], unique=False)
    op.create_index("ix_gcm_events_org_domain", "google_consent_mode_events", ["organization_id", "domain"], unique=False)
    op.create_index("ix_gcm_events_org_subject_hash", "google_consent_mode_events", ["organization_id", "subject_identifier_hash"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_gcm_events_org_subject_hash", table_name="google_consent_mode_events")
    op.drop_index("ix_gcm_events_org_domain", table_name="google_consent_mode_events")
    op.drop_index("ix_gcm_events_org_created", table_name="google_consent_mode_events")
    op.drop_index("ix_google_consent_mode_events_organization_id", table_name="google_consent_mode_events")
    op.drop_table("google_consent_mode_events")
