"""organization manifest verification events

Revision ID: 0035_organization_manifest_verification_events
Revises: 0034_organization_internal_signing_keys
Create Date: 2026-06-18 23:59:50.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0035_organization_manifest_verification_events"
down_revision: str | None = "0034_organization_internal_signing_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organization_governance_manifest_verification_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("manifest_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("verified_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_hash", sa.Boolean(), nullable=False),
        sa.Column("valid_signature", sa.Boolean(), nullable=False),
        sa.Column("trusted", sa.Boolean(), nullable=False),
        sa.Column("key_id", sa.String(length=128), nullable=True),
        sa.Column("key_status", sa.String(length=32), nullable=True),
        sa.Column("legacy_verification", sa.Boolean(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("recomputed_sha256", sa.String(length=64), nullable=False),
        sa.Column("signature_algorithm", sa.String(length=32), nullable=False),
        sa.Column("verification_result_json", sa.JSON(), nullable=False),
        sa.Column("caveat", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["manifest_id"],
            ["organization_governance_evidence_manifests.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["verified_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_org_governance_manifest_verification_events_org_manifest_verified",
        "organization_governance_manifest_verification_events",
        ["organization_id", "manifest_id", "verified_at"],
        unique=False,
    )
    op.create_index(
        "ix_org_governance_manifest_verification_events_org_trusted_verified",
        "organization_governance_manifest_verification_events",
        ["organization_id", "trusted", "verified_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_org_governance_manifest_verification_events_org_trusted_verified",
        table_name="organization_governance_manifest_verification_events",
    )
    op.drop_index(
        "ix_org_governance_manifest_verification_events_org_manifest_verified",
        table_name="organization_governance_manifest_verification_events",
    )
    op.drop_table("organization_governance_manifest_verification_events")
