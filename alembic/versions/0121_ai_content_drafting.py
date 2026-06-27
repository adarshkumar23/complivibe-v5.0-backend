"""ai content drafting

Revision ID: 0121_ai_content_drafting
Revises: 0120_webhooks_and_offboarding_automation
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0121_ai_content_drafting"
down_revision: str | None = "0120_webhooks_and_offboarding_automation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "org_ai_config",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_drafting_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("enabled_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["enabled_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", name="uq_org_ai_config_organization_id"),
    )

    op.create_table(
        "draft_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("draft_type", sa.String(length=50), nullable=False),
        sa.Column("context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("draft_output", sa.Text(), nullable=True),
        sa.Column("model_used", sa.String(length=100), nullable=True),
        sa.Column("prompt_used", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("applied", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "draft_type IN ('policy_content', 'risk_description', 'control_description', 'evidence_description', 'rca_summary')",
            name="ck_draft_requests_draft_type",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["applied_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_draft_requests_org_draft_type", "draft_requests", ["organization_id", "draft_type"], unique=False)
    op.create_index("ix_draft_requests_org_created_by", "draft_requests", ["organization_id", "created_by"], unique=False)
    op.create_index("ix_draft_requests_org_applied", "draft_requests", ["organization_id", "applied"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_draft_requests_org_applied", table_name="draft_requests")
    op.drop_index("ix_draft_requests_org_created_by", table_name="draft_requests")
    op.drop_index("ix_draft_requests_org_draft_type", table_name="draft_requests")
    op.drop_table("draft_requests")
    op.drop_table("org_ai_config")
