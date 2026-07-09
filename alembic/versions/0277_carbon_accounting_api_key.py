"""add dedicated carbon-accounting ingest API key table

Revision ID: 0270_carbon_accounting_api_key
Revises: 0269_attestation_token_revocation
Create Date: 2026-07-08 00:00:00.000000

POST /carbon-accounting/readings authenticated inbound requests by checking the raw
X-CompliVibe-Key against org_api_key_hash stored on OpenMetadata *lineage* integration
configs -- a completely unrelated feature. An org with no OpenMetadata integration
configured (the normal case for carbon accounting alone) had no key that could ever
match, so every ingest call 401'd with "Invalid API key" regardless of what key was
sent. This adds a dedicated, org-scoped ingest key table for carbon accounting,
provisioned via its own endpoint, so the two features are no longer coupled.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0277_carbon_accounting_api_key"
down_revision: str | None = "0276_vendor_annual_spend_amount"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "carbon_accounting_api_keys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("api_key_hash", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("organization_id", name="uq_carbon_accounting_api_keys_org"),
    )
    op.create_index(
        "ix_carbon_accounting_api_keys_hash",
        "carbon_accounting_api_keys",
        ["api_key_hash"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    op.drop_index("ix_carbon_accounting_api_keys_hash", table_name="carbon_accounting_api_keys")
    op.drop_table("carbon_accounting_api_keys")
