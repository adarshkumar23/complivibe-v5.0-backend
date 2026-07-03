"""ai policy drafting

Revision ID: 0179_ai_policy_drafting
Revises: 0178_board_scorecard_snapshots
Create Date: 2026-06-30 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0179_ai_policy_drafting"
down_revision: str | None = "0178_board_scorecard_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organization_ai_configurations",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("use_byo_credentials", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("groq_api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("azure_api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("azure_endpoint", sa.String(length=500), nullable=True),
        sa.Column("azure_deployment_name", sa.String(length=150), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE", name="fk_org_ai_cfg_org"),
        sa.PrimaryKeyConstraint("id", name="pk_org_ai_cfg"),
        sa.UniqueConstraint("organization_id", name="uq_org_ai_cfg_org"),
    )

    op.create_table(
        "ai_content_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_unit_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("content_type", sa.String(length=50), nullable=False),
        sa.Column("prompt_input", sa.Text(), nullable=False),
        sa.Column("draft_output", sa.Text(), nullable=False),
        sa.Column("provider_used", sa.String(length=20), nullable=False),
        sa.Column("used_byo_credentials", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("linked_policy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("content_type IN ('policy')", name="ck_ai_draft_content_type"),
        sa.CheckConstraint("provider_used IN ('groq', 'azure')", name="ck_ai_draft_provider"),
        sa.CheckConstraint("status IN ('draft', 'accepted', 'discarded')", name="ck_ai_draft_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE", name="fk_ai_draft_org"),
        sa.ForeignKeyConstraint(["business_unit_id"], ["business_units.id"], ondelete="SET NULL", name="fk_ai_draft_bu"),
        sa.ForeignKeyConstraint(["linked_policy_id"], ["compliance_policies.id"], ondelete="SET NULL", name="fk_ai_draft_policy"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT", name="fk_ai_draft_user"),
        sa.PrimaryKeyConstraint("id", name="pk_ai_draft"),
    )

    op.create_index("ix_ai_draft_org_status", "ai_content_drafts", ["organization_id", "status"], unique=False)
    op.create_index("ix_ai_draft_org_bu", "ai_content_drafts", ["organization_id", "business_unit_id"], unique=False)

    op.add_column(
        "compliance_policies",
        sa.Column("ai_drafted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "compliance_policies",
        sa.Column("source_ai_draft_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_policy_src_ai_draft",
        "compliance_policies",
        "ai_content_drafts",
        ["source_ai_draft_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_policy_src_ai_draft", "compliance_policies", type_="foreignkey")
    op.drop_column("compliance_policies", "source_ai_draft_id")
    op.drop_column("compliance_policies", "ai_drafted")

    op.drop_index("ix_ai_draft_org_bu", table_name="ai_content_drafts")
    op.drop_index("ix_ai_draft_org_status", table_name="ai_content_drafts")
    op.drop_table("ai_content_drafts")
    op.drop_table("organization_ai_configurations")
