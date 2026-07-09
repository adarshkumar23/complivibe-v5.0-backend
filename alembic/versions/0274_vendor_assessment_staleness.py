"""add risk_id linkage to vendor_assessments for overdue-assessment staleness cascade

Revision ID: 0270_vendor_assessment_staleness
Revises: 0269_attestation_token_revocation
Create Date: 2026-07-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0274_vendor_assessment_staleness"
down_revision: str | None = "0273_risk_dependencies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "vendor_assessments",
        sa.Column(
            "risk_id",
            sa.Uuid(),
            sa.ForeignKey("risks.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_vendor_assessments_org_risk",
        "vendor_assessments",
        ["organization_id", "risk_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_vendor_assessments_org_risk", table_name="vendor_assessments")
    op.drop_column("vendor_assessments", "risk_id")
