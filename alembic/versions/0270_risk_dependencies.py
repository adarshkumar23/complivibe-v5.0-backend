"""add risk_dependencies table for genuine risk-to-risk cascade tracking

Revision ID: 0270_risk_dependencies
Revises: 0269_attestation_token_revocation
Create Date: 2026-07-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0270_risk_dependencies"
down_revision: str | None = "0269_attestation_token_revocation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "risk_dependencies",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("upstream_risk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("downstream_risk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relationship_type", sa.String(length=32), nullable=False, server_default="cascades_to"),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["upstream_risk_id"], ["risks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["downstream_risk_id"], ["risks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "upstream_risk_id", "downstream_risk_id", name="uq_risk_dependency_edge"
        ),
        sa.CheckConstraint("upstream_risk_id != downstream_risk_id", name="ck_risk_dependency_no_self_loop"),
        sa.CheckConstraint(
            "relationship_type IN ('cascades_to', 'triggers', 'compounds')",
            name="ck_risk_dependency_relationship_type",
        ),
    )
    op.create_index("ix_risk_dependencies_organization_id", "risk_dependencies", ["organization_id"], unique=False)
    op.create_index("ix_risk_dependencies_upstream_risk_id", "risk_dependencies", ["upstream_risk_id"], unique=False)
    op.create_index(
        "ix_risk_dependencies_downstream_risk_id", "risk_dependencies", ["downstream_risk_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_risk_dependencies_downstream_risk_id", table_name="risk_dependencies")
    op.drop_index("ix_risk_dependencies_upstream_risk_id", table_name="risk_dependencies")
    op.drop_index("ix_risk_dependencies_organization_id", table_name="risk_dependencies")
    op.drop_table("risk_dependencies")
