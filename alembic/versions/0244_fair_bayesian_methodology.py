"""widen risk_quantification_runs methodology check constraint for fair_bayesian

Revision ID: 0244_fair_bayesian
Revises: 0243_export_control_compliance
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0244_fair_bayesian"
down_revision: str | None = "0243_export_control_compliance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Additive: allow the new methodology="fair_bayesian" value (real PyMC
    # Bayesian FAIR modeling) alongside the existing 'monte_carlo' and 'fair'
    # values. No data is altered or deleted; existing rows are untouched.
    op.drop_constraint(
        "ck_risk_quantification_runs_methodology",
        "risk_quantification_runs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_risk_quantification_runs_methodology",
        "risk_quantification_runs",
        "methodology IN ('monte_carlo', 'fair', 'fair_bayesian')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_risk_quantification_runs_methodology",
        "risk_quantification_runs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_risk_quantification_runs_methodology",
        "risk_quantification_runs",
        "methodology IN ('monte_carlo', 'fair')",
    )
