"""add quantified re-identification risk metric to synthetic datasets

Revision ID: 0232_synth_risk_metric
Revises: 0231_td_rights_lifecycle
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0232_synth_risk_metric"
down_revision: str | None = "0231_td_rights_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("synthetic_datasets", sa.Column("privacy_parameter", sa.Float(), nullable=True))
    op.add_column(
        "synthetic_datasets", sa.Column("reidentification_risk_score", sa.Float(), nullable=True)
    )
    op.create_check_constraint(
        "ck_synthetic_datasets_risk_score_range",
        "synthetic_datasets",
        "reidentification_risk_score IS NULL OR "
        "(reidentification_risk_score >= 0.0 AND reidentification_risk_score <= 1.0)",
    )
    op.create_check_constraint(
        "ck_synthetic_datasets_privacy_parameter_positive",
        "synthetic_datasets",
        "privacy_parameter IS NULL OR privacy_parameter > 0.0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_synthetic_datasets_privacy_parameter_positive", "synthetic_datasets", type_="check")
    op.drop_constraint("ck_synthetic_datasets_risk_score_range", "synthetic_datasets", type_="check")
    op.drop_column("synthetic_datasets", "reidentification_risk_score")
    op.drop_column("synthetic_datasets", "privacy_parameter")
