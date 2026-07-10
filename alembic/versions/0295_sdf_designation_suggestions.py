"""add sdf_designation_suggestions table for DPDP Significant Data Fiduciary auto-suggestion

Revision ID: 0295_sdf_designation_suggestions
Revises: 0294_dpdp_consent_minor_guardian_and_nominations
Create Date: 2026-07-10 00:10:00.000000

DPDP Rules 2025 (Rule 13) leaves exact volume/sensitivity thresholds for Significant Data
Fiduciary designation to be separately notified by the Central Government rather than
publishing a fixed numeric threshold in the Rules themselves. This table stores a
data-driven SUGGESTION only; a human must confirm before organizations.is_significant_data_fiduciary
is set (see app.privacy.services.sdf_designation_service).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0295_sdf_designation_suggestions"
down_revision: str | None = "0294_dpdp_consent_minor_guardian_and_nominations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sdf_designation_suggestions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("suggested_sdf", sa.Boolean(), nullable=False),
        sa.Column("sensitive_asset_count", sa.Integer(), nullable=False),
        sa.Column("total_asset_count", sa.Integer(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("confirmed_value", sa.Boolean(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["confirmed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_sdf_suggestions_org_created",
        "sdf_designation_suggestions",
        ["organization_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_sdf_suggestions_org_created", table_name="sdf_designation_suggestions")
    op.drop_table("sdf_designation_suggestions")
