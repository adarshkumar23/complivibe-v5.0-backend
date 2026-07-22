"""trial_codes: single-use trial redemption codes

Stage 1c-2 of the Free/Trial/Paid access model. Creates the trial_codes table.
Codes are stored as SHA-256 hex hashes only (plaintext lives out-of-band in a
CSV, never in the DB). Single-use is enforced at redemption time by an atomic
`redeemed_at IS NULL` claim.

Revision ID: 0330_trial_codes
Revises: 0329_access_model_free_plan
Create Date: 2026-07-22 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0330_trial_codes"
down_revision: str | None = "0329_access_model_free_plan"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trial_codes",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("code_prefix", sa.String(length=16), nullable=True),
        sa.Column("batch_label", sa.String(length=64), nullable=True),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("redeemed_by_org_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["redeemed_by_org_id"], ["organizations.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_trial_codes_code_hash", "trial_codes", ["code_hash"], unique=True)
    op.create_index("ix_trial_codes_redeemed_at", "trial_codes", ["redeemed_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_trial_codes_redeemed_at", table_name="trial_codes")
    op.drop_index("ix_trial_codes_code_hash", table_name="trial_codes")
    op.drop_table("trial_codes")
