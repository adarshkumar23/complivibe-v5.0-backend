"""standardize audit finding accepted risk status

Revision ID: f37a755f8aa6
Revises: 0201_align_ai_governance_review_types
Create Date: 2026-07-04 14:13:48.859530
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f37a755f8aa6'
down_revision: Union[str, Sequence[str], None] = '0201_align_ai_governance_review_types'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Standardize on the v2 accept-risk status value across the whole codebase.
    # The legacy v1 surface used "risk_accepted" for the same concept; migrating
    # existing rows prevents v1 read/schema mismatches for orgs that have used
    # the v2 accept-risk flow.
    op.execute("UPDATE audit_findings SET status = 'accepted_risk' WHERE status = 'risk_accepted'")


def downgrade() -> None:
    pass
