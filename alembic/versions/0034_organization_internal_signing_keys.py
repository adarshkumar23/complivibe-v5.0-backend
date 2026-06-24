"""organization internal signing keys

Revision ID: 0034_organization_internal_signing_keys
Revises: 0033_organization_governance_evidence_manifests
Create Date: 2026-06-18 23:59:30.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0034_organization_internal_signing_keys"
down_revision: str | None = "0033_organization_governance_evidence_manifests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organization_internal_signing_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key_id", sa.String(length=128), nullable=False),
        sa.Column("algorithm", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("purpose", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_org_internal_signing_keys_org_purpose_status",
        "organization_internal_signing_keys",
        ["organization_id", "purpose", "status"],
        unique=False,
    )
    op.create_index(
        "ix_org_internal_signing_keys_org_purpose_key_id",
        "organization_internal_signing_keys",
        ["organization_id", "purpose", "key_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_org_internal_signing_keys_org_purpose_key_id",
        table_name="organization_internal_signing_keys",
    )
    op.drop_index(
        "ix_org_internal_signing_keys_org_purpose_status",
        table_name="organization_internal_signing_keys",
    )
    op.drop_table("organization_internal_signing_keys")
