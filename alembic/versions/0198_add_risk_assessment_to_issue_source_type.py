"""add risk_assessment to issue source_type

Revision ID: 0198_add_risk_assessment_to_issue_source_type
Revises: 0197_add_timestamp_defaults_to_framework_review_tables
Create Date: 2026-07-03 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0198_add_risk_assessment_to_issue_source_type"
down_revision: str | None = "0197_add_timestamp_defaults_to_framework_review_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SOURCE_TYPES = (
    "'manual'",
    "'monitoring_alert'",
    "'audit_finding'",
    "'vendor_assessment'",
    "'external_report'",
    "'data_incident'",
    "'risk_assessment'",
)


def upgrade() -> None:
    op.drop_constraint("ck_issues_source_type", "issues", type_="check")
    op.create_check_constraint(
        "ck_issues_source_type",
        "issues",
        f"source_type IN ({', '.join(_SOURCE_TYPES)})",
    )


def downgrade() -> None:
    op.drop_constraint("ck_issues_source_type", "issues", type_="check")
    op.create_check_constraint(
        "ck_issues_source_type",
        "issues",
        "source_type IN ('manual', 'monitoring_alert', 'audit_finding', 'vendor_assessment', 'external_report', 'data_incident')",
    )
