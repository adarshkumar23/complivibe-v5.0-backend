"""align ai governance review types with ai system governance review types

Revision ID: 0200_align_ai_governance_review_types
Revises: 0199_audit_engagement_source_schedule_link
Create Date: 2026-07-04 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0200_align_ai_governance_review_types"
down_revision: str | None = "0199_audit_engagement_source_schedule_link"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RENAMES = {
    "initial_approval": "initial_review",
    "pre_deployment": "pre_production_review",
    "periodic": "periodic_review",
    "triggered": "change_review",
}


def upgrade() -> None:
    op.drop_constraint("ck_ai_governance_reviews_review_type", "ai_governance_reviews", type_="check")

    for old_value, new_value in _RENAMES.items():
        op.execute(
            sa.text(
                "UPDATE ai_governance_reviews SET review_type = :new_value WHERE review_type = :old_value"
            ).bindparams(new_value=new_value, old_value=old_value)
        )

    op.create_check_constraint(
        "ck_ai_governance_reviews_review_type",
        "ai_governance_reviews",
        "review_type IN ('initial_review', 'pre_production_review', 'periodic_review', 'change_review', 'retirement_review')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_ai_governance_reviews_review_type", "ai_governance_reviews", type_="check")

    for old_value, new_value in _RENAMES.items():
        op.execute(
            sa.text(
                "UPDATE ai_governance_reviews SET review_type = :old_value WHERE review_type = :new_value"
            ).bindparams(old_value=old_value, new_value=new_value)
        )

    op.create_check_constraint(
        "ck_ai_governance_reviews_review_type",
        "ai_governance_reviews",
        "review_type IN ('initial_approval', 'periodic', 'triggered', 'pre_deployment')",
    )
