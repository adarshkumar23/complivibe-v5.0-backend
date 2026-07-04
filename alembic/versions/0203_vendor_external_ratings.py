"""vendor external ratings

Revision ID: 0203_vendor_external_ratings
Revises: 0202_oidc_sso_support
Create Date: 2026-07-04 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0203_vendor_external_ratings"
down_revision: str | None = "0202_oidc_sso_support"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vendor_external_ratings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("signals_used", sa.JSON(), nullable=False),
        sa.Column("composite_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vendor_external_ratings_org_vendor", "vendor_external_ratings", ["organization_id", "vendor_id"], unique=False)
    op.create_index("ix_vendor_external_ratings_org_computed", "vendor_external_ratings", ["organization_id", "computed_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_vendor_external_ratings_org_computed", table_name="vendor_external_ratings")
    op.drop_index("ix_vendor_external_ratings_org_vendor", table_name="vendor_external_ratings")
    op.drop_table("vendor_external_ratings")
