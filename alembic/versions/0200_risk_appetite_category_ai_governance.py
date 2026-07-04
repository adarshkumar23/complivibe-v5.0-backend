"""widen risk_appetite_category_enum to include ai_governance

Revision ID: 0200_risk_appetite_category_ai_governance
Revises: 0199_audit_engagement_source_schedule_link
Create Date: 2026-07-04 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0200_risk_appetite_category_ai_governance"
down_revision: str | None = "0199_audit_engagement_source_schedule_link"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE risk_appetite_category_enum ADD VALUE IF NOT EXISTS 'ai_governance'")


def downgrade() -> None:
    # Postgres does not support removing a value from an ENUM type in place.
    # Rebuild the type without 'ai_governance', failing loudly if any row still uses it.
    op.execute(
        "ALTER TABLE risk_appetite_thresholds "
        "ALTER COLUMN risk_category TYPE varchar(32) USING risk_category::text"
    )
    op.execute("DROP TYPE risk_appetite_category_enum")
    op.execute(
        "CREATE TYPE risk_appetite_category_enum AS ENUM "
        "('operational', 'financial', 'compliance', 'reputational', 'technology', 'vendor')"
    )
    op.execute(
        "ALTER TABLE risk_appetite_thresholds "
        "ALTER COLUMN risk_category TYPE risk_appetite_category_enum "
        "USING risk_category::risk_appetite_category_enum"
    )
