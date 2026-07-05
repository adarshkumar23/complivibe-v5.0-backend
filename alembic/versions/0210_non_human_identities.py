"""add non human identities

Revision ID: 0210_non_human_identities
Revises: 0209_google_consent_mode_events
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0210_non_human_identities"
down_revision: str | None = "0209_google_consent_mode_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "non_human_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("identity_type", sa.String(length=32), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("permissions_scope", sa.Text(), nullable=True),
        sa.Column("external_ref", sa.String(length=255), nullable=True),
        sa.Column("environment", sa.String(length=64), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotation_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_orphaned", sa.Boolean(), nullable=False),
        sa.Column("orphan_detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("risk_reason", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["deleted_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_non_human_identities_organization_id", "non_human_identities", ["organization_id"], unique=False)
    op.create_index("ix_non_human_identities_org_type", "non_human_identities", ["organization_id", "identity_type"], unique=False)
    op.create_index("ix_non_human_identities_org_status", "non_human_identities", ["organization_id", "status"], unique=False)
    op.create_index("ix_non_human_identities_org_owner", "non_human_identities", ["organization_id", "owner_user_id"], unique=False)
    op.create_index("ix_non_human_identities_org_rotation_due", "non_human_identities", ["organization_id", "rotation_due_at"], unique=False)
    op.create_index("ix_non_human_identities_org_last_used", "non_human_identities", ["organization_id", "last_used_at"], unique=False)
    op.create_index("ix_non_human_identities_org_orphaned", "non_human_identities", ["organization_id", "is_orphaned"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_non_human_identities_org_orphaned", table_name="non_human_identities")
    op.drop_index("ix_non_human_identities_org_last_used", table_name="non_human_identities")
    op.drop_index("ix_non_human_identities_org_rotation_due", table_name="non_human_identities")
    op.drop_index("ix_non_human_identities_org_owner", table_name="non_human_identities")
    op.drop_index("ix_non_human_identities_org_status", table_name="non_human_identities")
    op.drop_index("ix_non_human_identities_org_type", table_name="non_human_identities")
    op.drop_index("ix_non_human_identities_organization_id", table_name="non_human_identities")
    op.drop_table("non_human_identities")
