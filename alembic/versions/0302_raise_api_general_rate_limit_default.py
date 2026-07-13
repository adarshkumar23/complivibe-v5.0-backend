"""raise api_general rate limit platform default from 60 to 300 per minute

Revision ID: 0302_raise_api_general_rate_limit_default
Revises: 0301_pbc_requests_backfill_into_pbc_items
Create Date: 2026-07-14 00:00:00.000000

`RateLimitService.ensure_platform_defaults` only inserts a platform-default
row when one doesn't already exist for that endpoint_group -- it never
updates `requests_per_minute` on a row that's already there. Any environment
that had already lazily seeded the `api_general` platform default before this
fix would stay stuck at the old 60/minute value forever, even after
DEFAULT_CONFIGS changed in code. This directly updates any existing platform
default row (organization_id IS NULL) for api_general still at the old value,
so the fix actually takes effect everywhere, not just brand-new databases.

Org-level overrides (a non-null organization_id row) are untouched -- an org
that explicitly configured its own api_general limit made a deliberate choice
that shouldn't be silently overwritten by a platform-default change.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0302_raise_api_general_rate_limit_default"
down_revision: str | None = "0301_pbc_requests_backfill_into_pbc_items"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("rate_limit_configs"):
        return

    bind.execute(
        sa.text(
            """
            UPDATE rate_limit_configs
            SET requests_per_minute = 300,
                requests_per_hour = 5000,
                requests_per_day = 50000,
                updated_at = now()
            WHERE organization_id IS NULL
              AND endpoint_group = 'api_general'
              AND requests_per_minute = 60
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("rate_limit_configs"):
        return

    bind.execute(
        sa.text(
            """
            UPDATE rate_limit_configs
            SET requests_per_minute = 60,
                requests_per_hour = 1000,
                requests_per_day = 10000,
                updated_at = now()
            WHERE organization_id IS NULL
              AND endpoint_group = 'api_general'
              AND requests_per_minute = 300
            """
        )
    )
