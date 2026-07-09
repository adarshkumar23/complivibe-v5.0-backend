"""add 'data_asset' to entity_risk_scores.entity_type CHECK constraint

The EntityRiskScoreComputeRequest Pydantic schema (ENTITY_TYPE_PATTERN) has always
accepted entity_type="data_asset" for POST /risk-scores/compute-entity, but the
DB CHECK constraint created in 0095_entity_level_risk_scoring.py only allowed
('vendor', 'asset', 'business_unit', 'framework'). Any data_asset compute-entity
call therefore passed schema validation and then hit an unhandled IntegrityError
(500) on INSERT. This migration widens the CHECK constraint to match the schema.

Revision ID: 0285_entity_risk_scores_add_data_asset_entity_type
Revises: 0284_trust_center_slug_confirmed_at
Create Date: 2026-07-09 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0285_entity_risk_scores_add_data_asset_entity_type"
down_revision: str | None = "0284_trust_center_slug_confirmed_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_CONSTRAINT_SQL = "entity_type IN ('vendor', 'asset', 'business_unit', 'framework')"
NEW_CONSTRAINT_SQL = "entity_type IN ('vendor', 'asset', 'data_asset', 'business_unit', 'framework')"


def upgrade() -> None:
    op.drop_constraint("ck_entity_risk_scores_entity_type", "entity_risk_scores", type_="check")
    op.create_check_constraint(
        "ck_entity_risk_scores_entity_type",
        "entity_risk_scores",
        NEW_CONSTRAINT_SQL,
    )


def downgrade() -> None:
    op.drop_constraint("ck_entity_risk_scores_entity_type", "entity_risk_scores", type_="check")
    op.create_check_constraint(
        "ck_entity_risk_scores_entity_type",
        "entity_risk_scores",
        OLD_CONSTRAINT_SQL,
    )
