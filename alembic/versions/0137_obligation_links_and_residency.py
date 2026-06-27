"""data obligation links and residency

Revision ID: 0137_obligation_links_and_residency
Revises: 0136_data_incidents
Create Date: 2026-06-26 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0137_obligation_links_and_residency"
down_revision: str | None = "0136_data_incidents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_asset_obligation_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("data_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("obligation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("link_type", sa.String(length=30), nullable=False),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("linked_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("link_type IN ('governed_by', 'subject_to', 'exempted_from')", name="ck_data_asset_obligation_links_link_type"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["data_asset_id"], ["data_assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["obligation_id"], ["obligations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["linked_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "data_asset_id",
            "obligation_id",
            name="uq_data_asset_obligation_links_org_asset_obligation",
        ),
    )
    op.create_index("ix_data_asset_obligation_links_org_asset", "data_asset_obligation_links", ["organization_id", "data_asset_id"], unique=False)
    op.create_index("ix_data_asset_obligation_links_org_obligation", "data_asset_obligation_links", ["organization_id", "obligation_id"], unique=False)
    op.create_index("ix_data_asset_obligation_links_org_link_type", "data_asset_obligation_links", ["organization_id", "link_type"], unique=False)

    op.create_table(
        "data_residency_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("required_countries", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("prohibited_countries", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("require_eea_only", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("require_domestic_only", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("legal_basis", sa.Text(), nullable=True),
        sa.Column("applies_to_classification_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("applies_to_sensitivity_tiers", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_data_residency_policies_org_active", "data_residency_policies", ["organization_id", "is_active"], unique=False)

    op.create_table(
        "data_residency_violations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("data_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("violation_type", sa.String(length=30), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("violating_locations", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'open'")),
        sa.Column("acknowledged_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("linked_incident_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "violation_type IN ('data_in_prohibited_country', 'data_outside_required_country', 'data_outside_eea', 'data_outside_domestic')",
            name="ck_data_residency_violations_violation_type",
        ),
        sa.CheckConstraint("status IN ('open', 'acknowledged', 'resolved', 'waived')", name="ck_data_residency_violations_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["data_asset_id"], ["data_assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_id"], ["data_residency_policies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["acknowledged_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_data_residency_violations_org_asset", "data_residency_violations", ["organization_id", "data_asset_id"], unique=False)
    op.create_index("ix_data_residency_violations_org_status", "data_residency_violations", ["organization_id", "status"], unique=False)
    op.create_index("ix_data_residency_violations_detected_at", "data_residency_violations", ["detected_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_data_residency_violations_detected_at", table_name="data_residency_violations")
    op.drop_index("ix_data_residency_violations_org_status", table_name="data_residency_violations")
    op.drop_index("ix_data_residency_violations_org_asset", table_name="data_residency_violations")
    op.drop_table("data_residency_violations")

    op.drop_index("ix_data_residency_policies_org_active", table_name="data_residency_policies")
    op.drop_table("data_residency_policies")

    op.drop_index("ix_data_asset_obligation_links_org_link_type", table_name="data_asset_obligation_links")
    op.drop_index("ix_data_asset_obligation_links_org_obligation", table_name="data_asset_obligation_links")
    op.drop_index("ix_data_asset_obligation_links_org_asset", table_name="data_asset_obligation_links")
    op.drop_table("data_asset_obligation_links")
