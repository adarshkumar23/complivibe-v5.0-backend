"""data observability scaffold marker

Revision ID: 0132_data_observability_scaffold
Revises: 0131_mlops_integrations
Create Date: 2026-06-26 00:00:00.000000
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0132_data_observability_scaffold"
down_revision: str | None = "0131_mlops_integrations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
