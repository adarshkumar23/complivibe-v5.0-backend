"""widen draft_requests draft_type check constraint to match AIDraftingService

The draft_requests.draft_type CHECK constraint (ck_draft_requests_draft_type,
added in 0121_ai_content_drafting) only ever allowed the original 5 draft
types: policy_content, risk_description, control_description,
evidence_description, rca_summary.

AIDraftingService.ALLOWED_DRAFT_TYPES has since grown to include
ai_risk_assessment_narrative, model_card_content, eu_act_conformity_narrative,
and ai_policy_draft (added across 0125_eu_act_workflows_and_ai_risk_assessments
and later application code) without a corresponding migration to widen this
constraint. Any create_draft() call using one of those 4 newer types passes
app-layer validation but fails at INSERT time with a bare, unhandled
IntegrityError -> 500 (e.g. POST /compliance/drafts/ai-policy).

Revision ID: 0270_widen_draft_requests_draft_type
Revises: 0269_attestation_token_revocation
Create Date: 2026-07-08 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0271_widen_draft_requests_draft_type"
down_revision: str | None = "0270_backfill_timestamp_server_defaults"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_TYPES = (
    "policy_content",
    "risk_description",
    "control_description",
    "evidence_description",
    "rca_summary",
)

NEW_TYPES = (
    *OLD_TYPES,
    "ai_risk_assessment_narrative",
    "model_card_content",
    "eu_act_conformity_narrative",
    "ai_policy_draft",
)


def _in_list(types: tuple[str, ...]) -> str:
    return ", ".join(f"'{t}'" for t in types)


def upgrade() -> None:
    op.drop_constraint("ck_draft_requests_draft_type", "draft_requests", type_="check")
    op.create_check_constraint(
        "ck_draft_requests_draft_type",
        "draft_requests",
        f"draft_type IN ({_in_list(NEW_TYPES)})",
    )


def downgrade() -> None:
    op.drop_constraint("ck_draft_requests_draft_type", "draft_requests", type_="check")
    op.create_check_constraint(
        "ck_draft_requests_draft_type",
        "draft_requests",
        f"draft_type IN ({_in_list(OLD_TYPES)})",
    )
