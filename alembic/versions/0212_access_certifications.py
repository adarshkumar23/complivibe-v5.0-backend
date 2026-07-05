"""add access certifications

Revision ID: 0212_access_certifications
Revises: 0211_pam_session_records
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0212_access_certifications"
down_revision: str | None = "0211_pam_session_records"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "access_certification_campaign",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("scope_type", sa.String(length=64), nullable=False),
        sa.Column("scope_config_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("launched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_access_certification_campaign_organization_id", "access_certification_campaign", ["organization_id"], unique=False)
    op.create_index("ix_access_cert_campaign_org_status", "access_certification_campaign", ["organization_id", "status"], unique=False)
    op.create_index("ix_access_cert_campaign_org_due", "access_certification_campaign", ["organization_id", "due_date"], unique=False)

    op.create_table(
        "access_certification_item",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_user_id", sa.Uuid(), nullable=False),
        sa.Column("system_key", sa.String(length=255), nullable=False),
        sa.Column("system_name", sa.String(length=255), nullable=False),
        sa.Column("access_level", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=True),
        sa.Column("decision_comment", sa.Text(), nullable=True),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["access_certification_campaign.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "user_id", "system_key", name="uq_access_cert_item_campaign_user_system"),
    )
    op.create_index("ix_access_certification_item_organization_id", "access_certification_item", ["organization_id"], unique=False)
    op.create_index("ix_access_cert_item_org_campaign", "access_certification_item", ["organization_id", "campaign_id"], unique=False)
    op.create_index("ix_access_cert_item_org_reviewer_status", "access_certification_item", ["organization_id", "reviewer_user_id", "status"], unique=False)
    op.create_index("ix_access_cert_item_org_user", "access_certification_item", ["organization_id", "user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_access_cert_item_org_user", table_name="access_certification_item")
    op.drop_index("ix_access_cert_item_org_reviewer_status", table_name="access_certification_item")
    op.drop_index("ix_access_cert_item_org_campaign", table_name="access_certification_item")
    op.drop_index("ix_access_certification_item_organization_id", table_name="access_certification_item")
    op.drop_table("access_certification_item")
    op.drop_index("ix_access_cert_campaign_org_due", table_name="access_certification_campaign")
    op.drop_index("ix_access_cert_campaign_org_status", table_name="access_certification_campaign")
    op.drop_index("ix_access_certification_campaign_organization_id", table_name="access_certification_campaign")
    op.drop_table("access_certification_campaign")
