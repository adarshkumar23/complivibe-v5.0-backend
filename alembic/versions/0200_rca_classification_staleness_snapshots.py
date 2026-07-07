"""add severity/issue-type snapshot columns for RCA + classification staleness detection

Revision ID: 0200_rca_classification_staleness_snapshots
Revises: 0199_audit_engagement_source_schedule_link
Create Date: 2026-07-07 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0200_rca_classification_staleness_snapshots"
down_revision: str | None = "0199_audit_engagement_source_schedule_link"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "root_cause_analyses",
        sa.Column("severity_at_creation", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "incident_classifications",
        sa.Column("classified_issue_type", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "incident_classifications",
        sa.Column("classified_severity", sa.String(length=20), nullable=True),
    )
    # Backfill existing rows from the current issue state so historical rows
    # don't spuriously appear "stale" the moment this migration runs.
    op.execute(
        """
        UPDATE root_cause_analyses
        SET severity_at_creation = issues.severity
        FROM issues
        WHERE issues.id = root_cause_analyses.issue_id
          AND root_cause_analyses.severity_at_creation IS NULL
        """
    )
    op.execute(
        """
        UPDATE incident_classifications
        SET classified_issue_type = issues.issue_type,
            classified_severity = issues.severity
        FROM issues
        WHERE issues.id = incident_classifications.issue_id
          AND incident_classifications.classified_issue_type IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("incident_classifications", "classified_severity")
    op.drop_column("incident_classifications", "classified_issue_type")
    op.drop_column("root_cause_analyses", "severity_at_creation")
