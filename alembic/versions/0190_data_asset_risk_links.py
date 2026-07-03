"""add data asset risk links

Revision ID: 0190_data_asset_risk_links
Revises: 0189_audit_scheduling_evidence_package_builder
Create Date: 2026-07-02 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0190_data_asset_risk_links"
down_revision: str | None = "0189_audit_scheduling_evidence_package_builder"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_asset_risk_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("data_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("risk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_darl_org_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["data_asset_id"], ["data_assets.id"], name="fk_darl_asset_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["risk_id"], ["risks.id"], name="fk_darl_risk_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_darl_created_by", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("data_asset_id", "risk_id", name="uq_darl_asset_risk"),
    )
    op.create_index("ix_darl_org_asset", "data_asset_risk_links", ["organization_id", "data_asset_id"], unique=False)
    op.create_index("ix_darl_org_risk", "data_asset_risk_links", ["organization_id", "risk_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_darl_org_risk", table_name="data_asset_risk_links")
    op.drop_index("ix_darl_org_asset", table_name="data_asset_risk_links")
    op.drop_table("data_asset_risk_links")
