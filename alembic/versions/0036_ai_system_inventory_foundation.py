"""ai system inventory foundation

Revision ID: 0036_ai_system_inventory_foundation
Revises: 0035_organization_manifest_verification_events
Create Date: 2026-06-19 10:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0036_ai_system_inventory_foundation"
down_revision: str | None = "0035_organization_manifest_verification_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_systems",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("system_type", sa.String(length=64), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=32), nullable=False),
        sa.Column("deployment_environment", sa.String(length=64), nullable=True),
        sa.Column("business_owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("technical_owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("vendor_name", sa.String(length=255), nullable=True),
        sa.Column("provider_name", sa.String(length=255), nullable=True),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("model_version", sa.String(length=128), nullable=True),
        sa.Column("intended_purpose", sa.Text(), nullable=True),
        sa.Column("use_case", sa.Text(), nullable=True),
        sa.Column("data_categories_json", sa.JSON(), nullable=True),
        sa.Column("user_groups_json", sa.JSON(), nullable=True),
        sa.Column("geography_json", sa.JSON(), nullable=True),
        sa.Column("tags_json", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["business_owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["technical_owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["archived_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_systems_organization_id", "ai_systems", ["organization_id"], unique=False)
    op.create_index("ix_ai_systems_org_lifecycle", "ai_systems", ["organization_id", "lifecycle_status"], unique=False)
    op.create_index("ix_ai_systems_org_system_type", "ai_systems", ["organization_id", "system_type"], unique=False)
    op.create_index(
        "ix_ai_systems_org_business_owner",
        "ai_systems",
        ["organization_id", "business_owner_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_systems_org_technical_owner",
        "ai_systems",
        ["organization_id", "technical_owner_user_id"],
        unique=False,
    )
    op.create_index("ix_ai_systems_org_archived", "ai_systems", ["organization_id", "archived_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ai_systems_org_archived", table_name="ai_systems")
    op.drop_index("ix_ai_systems_org_technical_owner", table_name="ai_systems")
    op.drop_index("ix_ai_systems_org_business_owner", table_name="ai_systems")
    op.drop_index("ix_ai_systems_org_system_type", table_name="ai_systems")
    op.drop_index("ix_ai_systems_org_lifecycle", table_name="ai_systems")
    op.drop_index("ix_ai_systems_organization_id", table_name="ai_systems")
    op.drop_table("ai_systems")
