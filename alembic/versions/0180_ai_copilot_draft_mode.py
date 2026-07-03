"""ai copilot draft mode

Revision ID: 0180_ai_copilot_draft_mode
Revises: 0179_ai_policy_drafting
Create Date: 2026-07-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0180_ai_copilot_draft_mode"
down_revision: str | None = "0179_ai_policy_drafting"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_draft_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("draft_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("refinement_instruction", sa.Text(), nullable=False),
        sa.Column("revised_output", sa.Text(), nullable=False),
        sa.Column("provider_used", sa.String(length=20), nullable=False),
        sa.Column("used_byo_credentials", sa.Boolean(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("provider_used IN ('groq', 'azure')", name="ck_ai_rev_provider"),
        sa.ForeignKeyConstraint(["draft_id"], ["ai_content_drafts.id"], ondelete="CASCADE", name="fk_ai_rev_draft"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE", name="fk_ai_rev_org"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT", name="fk_ai_rev_user"),
        sa.PrimaryKeyConstraint("id", name="pk_ai_rev"),
        sa.UniqueConstraint("draft_id", "revision_number", name="uq_ai_rev_draft_num"),
    )
    op.create_index("ix_ai_rev_draft", "ai_draft_revisions", ["draft_id"], unique=False)
    op.create_index("ix_ai_rev_org_created", "ai_draft_revisions", ["organization_id", "created_at"], unique=False)

    op.create_table(
        "ai_inline_suggestions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_unit_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("content_type", sa.String(length=50), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("suggestions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("linked_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider_used", sa.String(length=20), nullable=False),
        sa.Column("used_byo_credentials", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("content_type IN ('policy', 'control', 'risk')", name="ck_ai_sugg_content_type"),
        sa.CheckConstraint("provider_used IN ('groq', 'azure')", name="ck_ai_sugg_provider"),
        sa.CheckConstraint("status IN ('pending', 'applied', 'dismissed')", name="ck_ai_sugg_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE", name="fk_ai_sugg_org"),
        sa.ForeignKeyConstraint(["business_unit_id"], ["business_units.id"], ondelete="SET NULL", name="fk_ai_sugg_bu"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT", name="fk_ai_sugg_user"),
        sa.PrimaryKeyConstraint("id", name="pk_ai_sugg"),
    )
    op.create_index(
        "ix_ai_sugg_org_type",
        "ai_inline_suggestions",
        ["organization_id", "content_type"],
        unique=False,
    )
    op.create_index("ix_ai_sugg_org_status", "ai_inline_suggestions", ["organization_id", "status"], unique=False)
    op.create_index(
        "ix_ai_sugg_org_bu",
        "ai_inline_suggestions",
        ["organization_id", "business_unit_id"],
        unique=False,
    )

    # Extend draft content types beyond policy-only.
    op.drop_constraint("ck_ai_draft_content_type", "ai_content_drafts", type_="check")
    op.create_check_constraint(
        "ck_ai_draft_content_type",
        "ai_content_drafts",
        "content_type IN ('policy', 'control', 'risk')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_ai_draft_content_type", "ai_content_drafts", type_="check")
    op.create_check_constraint(
        "ck_ai_draft_content_type",
        "ai_content_drafts",
        "content_type IN ('policy')",
    )

    op.drop_index("ix_ai_sugg_org_bu", table_name="ai_inline_suggestions")
    op.drop_index("ix_ai_sugg_org_status", table_name="ai_inline_suggestions")
    op.drop_index("ix_ai_sugg_org_type", table_name="ai_inline_suggestions")
    op.drop_table("ai_inline_suggestions")

    op.drop_index("ix_ai_rev_org_created", table_name="ai_draft_revisions")
    op.drop_index("ix_ai_rev_draft", table_name="ai_draft_revisions")
    op.drop_table("ai_draft_revisions")
