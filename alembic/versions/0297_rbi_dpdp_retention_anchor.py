"""add relationship_end_date anchor to data_subject_requests for RBI-DPDP retention reconciliation

Revision ID: 0297_rbi_dpdp_retention_anchor
Revises: 0296_dsr_grievance_retention_conflict_nomination
Create Date: 2026-07-10 00:30:00.000000

The RBI-DPDP reconciliation engine (app.privacy.services.rbi_dpdp_reconciliation_service)
computes retention floors (e.g. RBI KYC Master Direction: 5 years from the end of the
customer relationship) relative to a relationship/account-closure end date. This column
lets a handler record that anchor date on an erasure request; without it the engine
cannot confirm an exact retention-floor expiry and treats the request as blocked pending
manual confirmation rather than guessing a date.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0297_rbi_dpdp_retention_anchor"
down_revision: str | None = "0296_dsr_grievance_retention_conflict_nomination"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "data_subject_requests",
        sa.Column("relationship_end_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("data_subject_requests", "relationship_end_date")
