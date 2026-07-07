"""add baseline_model_version to ai_monitoring_configs

Revision ID: 0200_ai_monitoring_config_baseline_model_version
Revises: 0199_audit_engagement_source_schedule_link
Create Date: 2026-07-07 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0200_ai_monitoring_config_baseline_model_version"
down_revision: str | None = "0199_audit_engagement_source_schedule_link"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_monitoring_configs",
        sa.Column("baseline_model_version", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ai_monitoring_configs", "baseline_model_version")
