"""consent cookies and privacy notices

Revision ID: 0140_consent_cookie_notice
Revises: 0139_dsar_rights_tracker
Create Date: 2026-06-26 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0140_consent_cookie_notice"
down_revision: str | None = "0139_dsar_rights_tracker"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "privacy_notices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False, server_default=sa.text("'en'")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("frameworks", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('draft', 'published', 'archived')", name="ck_privacy_notices_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["published_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_privacy_notices_org_status", "privacy_notices", ["organization_id", "status"], unique=False)
    op.create_index("ix_privacy_notices_org_lang_status", "privacy_notices", ["organization_id", "language", "status"], unique=False)

    op.create_table(
        "notice_user_acknowledgements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["notice_id"], ["privacy_notices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("notice_id", "user_id", name="uq_notice_ack_notice_user"),
    )
    op.create_index("ix_notice_acks_org_notice", "notice_user_acknowledgements", ["organization_id", "notice_id"], unique=False)
    op.create_index("ix_notice_acks_user_time", "notice_user_acknowledgements", ["user_id", "acknowledged_at"], unique=False)

    op.create_table(
        "consent_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("processing_activity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notice_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("subject_identifier", sa.String(length=500), nullable=False),
        sa.Column("subject_identifier_hash", sa.String(length=64), nullable=False),
        sa.Column("consent_mechanism", sa.String(length=50), nullable=False),
        sa.Column("consent_version", sa.String(length=50), nullable=True),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawal_reason", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "consent_mechanism IN ('explicit_checkbox', 'cookie_banner', 'written_form', 'verbal_recorded', 'api_consent', 'implied')",
            name="ck_consent_records_mechanism",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["processing_activity_id"], ["processing_activities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["notice_id"], ["privacy_notices.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_consent_records_org_activity", "consent_records", ["organization_id", "processing_activity_id"], unique=False)
    op.create_index("ix_consent_records_org_subject_hash", "consent_records", ["organization_id", "subject_identifier_hash"], unique=False)
    op.create_index("ix_consent_records_org_granted_activity", "consent_records", ["organization_id", "granted", "processing_activity_id"], unique=False)
    op.create_index("ix_consent_records_expiry_granted", "consent_records", ["expiry_date", "granted"], unique=False)

    op.create_table(
        "cookie_registries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("domain", sa.String(length=500), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=255), nullable=True),
        sa.Column("duration", sa.String(length=100), nullable=True),
        sa.Column("is_third_party", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default=sa.text("'manual'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "category IN ('strictly_necessary', 'functional', 'analytics', 'marketing', 'unknown')",
            name="ck_cookie_registries_category",
        ),
        sa.CheckConstraint("source IN ('manual', 'scan_report')", name="ck_cookie_registries_source"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", "domain", name="uq_cookie_registry_org_name_domain"),
    )
    op.create_index("ix_cookie_registries_org_category", "cookie_registries", ["organization_id", "category"], unique=False)
    op.create_index("ix_cookie_registries_org_active", "cookie_registries", ["organization_id", "is_active"], unique=False)

    op.create_table(
        "consent_banner_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("banner_title", sa.String(length=255), nullable=False, server_default=sa.text("'Cookie Preferences'")),
        sa.Column("banner_body", sa.Text(), nullable=False),
        sa.Column("accept_all_text", sa.String(length=100), nullable=False, server_default=sa.text("'Accept All'")),
        sa.Column("reject_all_text", sa.String(length=100), nullable=False, server_default=sa.text("'Reject All'")),
        sa.Column("manage_text", sa.String(length=100), nullable=False, server_default=sa.text("'Manage Preferences'")),
        sa.Column(
            "enabled_categories",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[\"strictly_necessary\",\"functional\",\"analytics\",\"marketing\"]'::jsonb"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", name="uq_consent_banner_configs_org"),
    )


def downgrade() -> None:
    op.drop_table("consent_banner_configs")

    op.drop_index("ix_cookie_registries_org_active", table_name="cookie_registries")
    op.drop_index("ix_cookie_registries_org_category", table_name="cookie_registries")
    op.drop_table("cookie_registries")

    op.drop_index("ix_consent_records_expiry_granted", table_name="consent_records")
    op.drop_index("ix_consent_records_org_granted_activity", table_name="consent_records")
    op.drop_index("ix_consent_records_org_subject_hash", table_name="consent_records")
    op.drop_index("ix_consent_records_org_activity", table_name="consent_records")
    op.drop_table("consent_records")

    op.drop_index("ix_notice_acks_user_time", table_name="notice_user_acknowledgements")
    op.drop_index("ix_notice_acks_org_notice", table_name="notice_user_acknowledgements")
    op.drop_table("notice_user_acknowledgements")

    op.drop_index("ix_privacy_notices_org_lang_status", table_name="privacy_notices")
    op.drop_index("ix_privacy_notices_org_status", table_name="privacy_notices")
    op.drop_table("privacy_notices")
