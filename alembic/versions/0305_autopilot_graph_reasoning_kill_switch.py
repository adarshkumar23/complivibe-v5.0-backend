"""add autopilot_graph_reasoning_enabled kill-switch

Revision ID: 0305_autopilot_graph_reasoning
Revises: 0304_compound_insights
Create Date: 2026-07-15 14:00:00.000000

Interconnection Phase 5 -- Autopilot cross-domain graph-aware reasoning.
Adds an INDEPENDENT per-org kill-switch that enables ONLY the new cross-domain
candidate generation, without touching base Autopilot's existing behavior. It
defaults OFF (opt-in on top of the base Autopilot opt-in): most-restrictive-wins
across base opt-in, this kill-switch, and the per-org confidence threshold.

This phase's v1 is suggestion-only -- cross-domain-sourced candidates always
route to human approval -- so this flag governs only whether the new candidates
are generated at all, never whether anything auto-executes.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0305_autopilot_graph_reasoning"
down_revision: str | None = "0304_compound_insights"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organization_governance_settings",
        sa.Column(
            "autopilot_graph_reasoning_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("organization_governance_settings", "autopilot_graph_reasoning_enabled")
