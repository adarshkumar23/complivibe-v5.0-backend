"""make offboarding successor optional

Revision ID: a6947935ab21
Revises: 0198_add_risk_assessment_to_issue_source_type
Create Date: 2026-07-04 07:30:29.672629
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a6947935ab21'
down_revision: Union[str, Sequence[str], None] = '0198_add_risk_assessment_to_issue_source_type'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "offboarding_records",
        "successor_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "offboarding_records",
        "successor_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
