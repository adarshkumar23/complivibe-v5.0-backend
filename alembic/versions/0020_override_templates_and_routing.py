"""override templates and conditional routing

Revision ID: 0020_override_templates_and_routing
Revises: 0019_governed_override_workflow
Create Date: 2026-06-19 03:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0020_override_templates_and_routing"
down_revision: Union[str, Sequence[str], None] = "0019_governed_override_workflow"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "governance_override_templates",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("override_type", sa.String(length=64), nullable=False),
        sa.Column("target_entity_type", sa.String(length=64), nullable=False),
        sa.Column("requested_action", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("default_required_approvals", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("approver_role_names_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("condition_rules_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_override_templates_org_status", "governance_override_templates", ["organization_id", "status"], unique=False)
    op.create_index("ix_override_templates_org_override_type", "governance_override_templates", ["organization_id", "override_type"], unique=False)
    op.create_index("ix_override_templates_org_target", "governance_override_templates", ["organization_id", "target_entity_type"], unique=False)
    op.create_index("ix_override_templates_org_action", "governance_override_templates", ["organization_id", "requested_action"], unique=False)

    op.create_table(
        "governance_override_template_versions",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("override_type", sa.String(length=64), nullable=False),
        sa.Column("target_entity_type", sa.String(length=64), nullable=False),
        sa.Column("requested_action", sa.String(length=64), nullable=False),
        sa.Column("default_required_approvals", sa.Integer(), nullable=False),
        sa.Column("approver_role_names_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("condition_rules_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["governance_override_templates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_override_template_versions_org_template",
        "governance_override_template_versions",
        ["organization_id", "template_id"],
        unique=False,
    )

    op.add_column("governance_override_requests", sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("governance_override_requests", sa.Column("template_version", sa.Integer(), nullable=True))
    op.add_column(
        "governance_override_requests",
        sa.Column("routing_context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "governance_override_requests",
        sa.Column("approver_role_names_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_foreign_key(
        "fk_override_requests_template_id",
        "governance_override_requests",
        "governance_override_templates",
        ["template_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_override_requests_org_template",
        "governance_override_requests",
        ["organization_id", "template_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_override_requests_org_template", table_name="governance_override_requests")
    op.drop_constraint("fk_override_requests_template_id", "governance_override_requests", type_="foreignkey")
    op.drop_column("governance_override_requests", "approver_role_names_json")
    op.drop_column("governance_override_requests", "routing_context_json")
    op.drop_column("governance_override_requests", "template_version")
    op.drop_column("governance_override_requests", "template_id")

    op.drop_index("ix_override_template_versions_org_template", table_name="governance_override_template_versions")
    op.drop_table("governance_override_template_versions")

    op.drop_index("ix_override_templates_org_action", table_name="governance_override_templates")
    op.drop_index("ix_override_templates_org_target", table_name="governance_override_templates")
    op.drop_index("ix_override_templates_org_override_type", table_name="governance_override_templates")
    op.drop_index("ix_override_templates_org_status", table_name="governance_override_templates")
    op.drop_table("governance_override_templates")
