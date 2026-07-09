"""add risk_id linkage to bribery_risk_assessments for high-risk escalation (G2)

A "high" anti-bribery risk finding that is inconsistent with a vendor's overall
risk_tier previously only set an inert `inconsistent_with_vendor_overall_risk_tier`
context flag -- nothing acted on it. This adds a `risk_id` column (mirroring the
same idempotency pattern used by VendorConcentrationRiskDetection.risk_id and
SanctionsScreenResult's risk-tier escalation in
app/satellites/tprm_intelligence/sanctions_screening.py) so
BriberyRiskScoringService can both escalate the vendor's risk_tier when it is
under-tiered and create/link a single Risk register entry for the finding,
without creating a duplicate Risk on every subsequent recompute.

Revision ID: 0285_bribery_risk_assessment_escalation
Revises: 0284_trust_center_slug_confirmed_at
Create Date: 2026-07-09 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0285_bribery_risk_assessment_escalation"
down_revision: str | None = "0284_trust_center_slug_confirmed_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bribery_risk_assessments",
        sa.Column("risk_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_bribery_risk_assessments_risk_id",
        "bribery_risk_assessments",
        "risks",
        ["risk_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_bribery_risk_assessments_org_risk",
        "bribery_risk_assessments",
        ["organization_id", "risk_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_bribery_risk_assessments_org_risk", table_name="bribery_risk_assessments")
    op.drop_constraint("fk_bribery_risk_assessments_risk_id", "bribery_risk_assessments", type_="foreignkey")
    op.drop_column("bribery_risk_assessments", "risk_id")
