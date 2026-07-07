"""generic attestation tokens

Revision ID: 0260_generic_attestation_tokens
Revises: 0259_governance_autopilot_auto_execution
Create Date: 2026-07-07 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0260_generic_attestation_tokens"
down_revision: str | Sequence[str] | None = "0259_governance_autopilot_auto_execution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "attestation_tokens",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=64), nullable=False),
        sa.Column("scope_json", sa.JSON(), nullable=True),
        sa.Column("scope_checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("linked_entity_type", sa.String(length=64), nullable=False),
        sa.Column("linked_entity_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("validation_count", sa.Integer(), nullable=False),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
        sa.CheckConstraint("status IN ('active', 'revoked', 'expired')", name="ck_attestation_tokens_status"),
    )
    op.create_index("ix_attestation_tokens_token_hash", "attestation_tokens", ["token_hash"], unique=False)
    op.create_index("ix_attestation_tokens_org_status", "attestation_tokens", ["organization_id", "status"], unique=False)
    op.create_index("ix_attestation_tokens_org_purpose", "attestation_tokens", ["organization_id", "purpose"], unique=False)
    op.create_index(
        "ix_attestation_tokens_org_entity",
        "attestation_tokens",
        ["organization_id", "linked_entity_type", "linked_entity_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_attestation_tokens_org_entity", table_name="attestation_tokens")
    op.drop_index("ix_attestation_tokens_org_purpose", table_name="attestation_tokens")
    op.drop_index("ix_attestation_tokens_org_status", table_name="attestation_tokens")
    op.drop_index("ix_attestation_tokens_token_hash", table_name="attestation_tokens")
    op.drop_table("attestation_tokens")
