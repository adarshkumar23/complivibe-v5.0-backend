"""access model foundation: add 'free' to subscription_plan CHECK

Stage 1c-1 of the Free/Trial/Paid access model. Adds the 'free' plan code
to the organizations.subscription_plan CHECK constraint. 'trial' is already
permitted by the existing constraint (added in 0173, preserved through 0251),
so no change is needed for the new Trial plan row.

No new columns: the per-plan record_caps live inside subscription_plans.features
(JSONB). Plan rows (free/trial) are seeded by BillingService.ensure_default_plans
from DEFAULT_PLANS, not by this migration.

Revision ID: 0329_access_model_free_plan
Revises: 0328_patent_scoped_key_p9_ingest
Create Date: 2026-07-22 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0329_access_model_free_plan"
down_revision: str | None = "0328_patent_scoped_key_p9_ingest"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_organizations_subscription_plan", "organizations", type_="check")
    op.create_check_constraint(
        "ck_organizations_subscription_plan",
        "organizations",
        "subscription_plan IN ('trial','starter','growth','enterprise','usage_flex','free')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_organizations_subscription_plan", "organizations", type_="check")
    op.create_check_constraint(
        "ck_organizations_subscription_plan",
        "organizations",
        "subscription_plan IN ('trial','starter','growth','enterprise','usage_flex')",
    )
