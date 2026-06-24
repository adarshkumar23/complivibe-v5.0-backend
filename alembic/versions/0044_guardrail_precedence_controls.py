"""guardrail precedence and enforcement controls

Revision ID: 0044_guardrail_precedence_controls
Revises: 0043_ai_system_governance_guardrails
Create Date: 2026-06-19 23:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0044_guardrail_precedence_controls"
down_revision: str | None = "0043_ai_system_governance_guardrails"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_system_governance_freeze_windows",
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
    )
    op.add_column(
        "ai_system_governance_freeze_windows",
        sa.Column("enforcement_level", sa.String(length=16), nullable=False, server_default="block"),
    )
    op.add_column(
        "ai_system_governance_freeze_windows",
        sa.Column("override_allowed", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "ai_system_governance_freeze_windows",
        sa.Column("precedence_notes", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ai_system_governance_freeze_windows", "precedence_notes")
    op.drop_column("ai_system_governance_freeze_windows", "override_allowed")
    op.drop_column("ai_system_governance_freeze_windows", "enforcement_level")
    op.drop_column("ai_system_governance_freeze_windows", "priority")
