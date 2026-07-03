"""add incident trigger type to customer commitments

Revision ID: 0191_customer_commitment_incident_trigger_type
Revises: 0190_data_asset_risk_links
Create Date: 2026-07-02 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0191_customer_commitment_incident_trigger_type"
down_revision: str | None = "0190_data_asset_risk_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "customer_commitments",
        sa.Column("triggering_incident_type", sa.String(length=100), nullable=True),
    )
    op.create_index(
        "ix_customer_commitments_org_trigger_incident",
        "customer_commitments",
        ["organization_id", "triggering_incident_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_customer_commitments_org_trigger_incident", table_name="customer_commitments")
    op.drop_column("customer_commitments", "triggering_incident_type")
