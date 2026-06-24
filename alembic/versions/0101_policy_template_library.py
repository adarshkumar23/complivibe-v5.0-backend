"""policy template library

Revision ID: 0101_policy_template_library
Revises: 0100_policy_exception_management
Create Date: 2026-06-24 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0101_policy_template_library"
down_revision: str | None = "0100_policy_exception_management"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "policy_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("framework_tags", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False, server_default=sa.text("'1.0'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "category IN ('Security', 'Privacy', 'Operations', 'HR', 'Legal', 'AI Governance', 'Compliance')",
            name="ck_policy_templates_category",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_policy_templates_slug"),
    )
    op.create_index("ix_policy_templates_category", "policy_templates", ["category"], unique=False)
    op.create_index("ix_policy_templates_is_active", "policy_templates", ["is_active"], unique=False)
    op.create_index(
        "ix_policy_templates_framework_tags_gin",
        "policy_templates",
        ["framework_tags"],
        unique=False,
        postgresql_using="gin",
    )

    op.create_table(
        "policy_template_clones",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cloned_policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cloned_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cloned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("customization_notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["policy_templates.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["cloned_policy_id"], ["compliance_policies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["cloned_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_policy_template_clones_org_template",
        "policy_template_clones",
        ["organization_id", "template_id"],
        unique=False,
    )
    op.create_index(
        "ix_policy_template_clones_org_policy",
        "policy_template_clones",
        ["organization_id", "cloned_policy_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_policy_template_clones_org_policy", table_name="policy_template_clones")
    op.drop_index("ix_policy_template_clones_org_template", table_name="policy_template_clones")
    op.drop_table("policy_template_clones")

    op.drop_index("ix_policy_templates_framework_tags_gin", table_name="policy_templates")
    op.drop_index("ix_policy_templates_is_active", table_name="policy_templates")
    op.drop_index("ix_policy_templates_category", table_name="policy_templates")
    op.drop_table("policy_templates")
