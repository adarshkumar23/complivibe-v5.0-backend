"""per-subsystem inbound ingest keys (decouple PAM/lineage/cookies/consent/security/access-monitoring)

Creates subsystem_ingest_keys: one inbound machine-ingest key per (organization,
key_type), replacing the single shared OpenMetadata/data-lineage integration key that
all six inbound subsystems previously authenticated against. Resolution is an indexed
hash lookup (ix_subsystem_ingest_keys_api_key_hash), not the old O(active-orgs)
decrypt-and-compare loop, and is scoped to one key_type so a key leaked from one
subsystem cannot authenticate another.

NO automatic data backfill: the previous shared key's raw value is unrecoverable (only
its hash was stored, inside the encrypted OpenMetadata config), and copying that hash
into every subsystem row would re-create the very sharing this closes. New per-subsystem
keys must be RE-ISSUED and distributed -- see
docs/runbooks/subsystem_ingest_key_reissuance.md and
scripts/reissue_subsystem_ingest_keys.py. Until re-issued, inbound ingest for an org
returns 401; existing integrations must be handed their new per-subsystem keys.

All identifiers are < 63 bytes (Postgres limit): table subsystem_ingest_keys (21),
uq_subsystem_ingest_keys_org_type (33), ck_subsystem_ingest_keys_key_type (33),
ix_subsystem_ingest_keys_api_key_hash (37).

Revision ID: 0317_subsystem_ingest_keys
Revises: 0316_control_exception_four_eyes
Create Date: 2026-07-20 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0317_subsystem_ingest_keys"
down_revision: str | None = "0316_control_exception_four_eyes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "subsystem_ingest_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("key_type", sa.String(length=32), nullable=False),
        sa.Column("api_key_hash", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "key_type IN ('lineage', 'cookies', 'consent', 'security', 'access_monitoring', 'pam')",
            name="ck_subsystem_ingest_keys_key_type",
        ),
        sa.UniqueConstraint("organization_id", "key_type", name="uq_subsystem_ingest_keys_org_type"),
    )
    op.create_index("ix_subsystem_ingest_keys_api_key_hash", "subsystem_ingest_keys", ["api_key_hash"])


def downgrade() -> None:
    op.drop_index("ix_subsystem_ingest_keys_api_key_hash", table_name="subsystem_ingest_keys")
    op.drop_table("subsystem_ingest_keys")
