"""board scorecard and executive narrative report types

Revision ID: 0116_board_scorecard_and_executive_narrative
Revises: 0115_remediation_and_incident_classification
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0116_board_scorecard_and_executive_narrative"
down_revision: str | None = "0115_remediation_and_incident_classification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # No schema changes required.
    # compliance_reports.report_type is VARCHAR and new report types are enabled at service/schema layer.
    pass


def downgrade() -> None:
    pass
