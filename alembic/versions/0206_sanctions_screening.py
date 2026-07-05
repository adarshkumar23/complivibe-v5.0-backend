"""sanctions screening

Revision ID: 0206_sanctions_screening
Revises: 0205_aml_kyc_checks
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0206_sanctions_screening"
down_revision: str | None = "0205_aml_kyc_checks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "sanctions_match_threshold",
            sa.Numeric(5, 4),
            nullable=False,
            server_default=sa.text("0.8500"),
        ),
    )
    op.create_table(
        "sanctions_entities",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("caption", sa.String(length=1024), nullable=False),
        sa.Column("schema_type", sa.String(length=100), nullable=False),
        sa.Column("countries", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("datasets", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("properties", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sanctions_entities_caption", "sanctions_entities", ["caption"], unique=False)
    op.create_index("ix_sanctions_entities_schema", "sanctions_entities", ["schema_type"], unique=False)
    op.create_table(
        "sanctions_screen_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.String(length=255), nullable=False),
        sa.Column("list_name", sa.String(length=255), nullable=False),
        sa.Column("screened_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("match_found", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("match_details", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("cleared_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["cleared_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sanctions_screen_results_org_vendor", "sanctions_screen_results", ["organization_id", "vendor_id"], unique=False)
    op.create_index("ix_sanctions_screen_results_org_screened", "sanctions_screen_results", ["organization_id", "screened_at"], unique=False)
    op.create_index("ix_sanctions_screen_results_org_entity", "sanctions_screen_results", ["organization_id", "entity_type", "entity_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_sanctions_screen_results_org_entity", table_name="sanctions_screen_results")
    op.drop_index("ix_sanctions_screen_results_org_screened", table_name="sanctions_screen_results")
    op.drop_index("ix_sanctions_screen_results_org_vendor", table_name="sanctions_screen_results")
    op.drop_table("sanctions_screen_results")
    op.drop_index("ix_sanctions_entities_schema", table_name="sanctions_entities")
    op.drop_index("ix_sanctions_entities_caption", table_name="sanctions_entities")
    op.drop_table("sanctions_entities")
    op.drop_column("organizations", "sanctions_match_threshold")
