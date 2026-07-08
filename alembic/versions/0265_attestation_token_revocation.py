"""add revocation bookkeeping columns to attestation_tokens

Revision ID: 0265_attestation_token_revocation
Revises: 0264_ai_monitoring_config_baseline_model_version
Create Date: 2026-07-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0265_attestation_token_revocation"
down_revision: str | None = "0264_ai_monitoring_config_baseline_model_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "attestation_tokens",
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "attestation_tokens",
        sa.Column(
            "revoked_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "attestation_tokens",
        sa.Column("revocation_reason", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("attestation_tokens", "revocation_reason")
    op.drop_column("attestation_tokens", "revoked_by_user_id")
    op.drop_column("attestation_tokens", "revoked_at")
