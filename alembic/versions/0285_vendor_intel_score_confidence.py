"""add confidence field + nullable score to vendor security rating / threat intel

Revision ID: 0285_vendor_intel_score_confidence
Revises: 0284_trust_center_slug_confirmed_at
Create Date: 2026-07-09 00:00:00.000000

Root-cause fix for G6 item 1: vendor security-rating / threat-intelligence scores pull
from 4 (or 3) independent external signals. In this environment 1-2 are always skipped
(no API key configured) and the rest frequently error/rate-limit against real domains.
The scoring math already excluded missing/errored signals from the weighted average
*when at least one signal was available*, but silently collapsed to a hardcoded 0.0 the
moment zero signals responded -- indistinguishable from "we checked, it's terrible"
(security rating) or "we checked, it's clean" (threat intel, where 0.0 is a false
negative) even though it actually meant "we have no data at all".

This migration:
  - Makes `composite_score` / `threat_score` nullable so "no data this run" can be
    stored honestly instead of as a fabricated extreme value.
  - Adds a `confidence` column (0-100) recording what percentage of the total scoring
    weight was actually backed by real signal data, so callers can tell a confident
    reading apart from a thin/empty one.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0285_vendor_intel_score_confidence"
down_revision: str | None = "0284_trust_center_slug_confirmed_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("vendor_external_ratings", "composite_score", existing_type=sa.Numeric(5, 2), nullable=True)
    op.add_column(
        "vendor_external_ratings",
        sa.Column("confidence", sa.Numeric(5, 2), nullable=False, server_default="0"),
    )

    op.alter_column("vendor_threat_intelligence", "threat_score", existing_type=sa.Numeric(5, 2), nullable=True)
    op.add_column(
        "vendor_threat_intelligence",
        sa.Column("confidence", sa.Numeric(5, 2), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("vendor_threat_intelligence", "confidence")
    op.alter_column("vendor_threat_intelligence", "threat_score", existing_type=sa.Numeric(5, 2), nullable=False)

    op.drop_column("vendor_external_ratings", "confidence")
    op.alter_column("vendor_external_ratings", "composite_score", existing_type=sa.Numeric(5, 2), nullable=False)
