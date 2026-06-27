"""issue-to-policy and issue-to-control linking

Revision ID: 0114_issue_policy_and_control_links
Revises: 0113_general_escalation_and_breach_workflow
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0114_issue_policy_and_control_links"
down_revision: str | None = "0113_general_escalation_and_breach_workflow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "issue_policy_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("link_type", sa.String(length=50), nullable=False),
        sa.Column("linked_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("link_type IN ('violated', 'related')", name="ck_issue_policy_links_link_type"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_id"], ["compliance_policies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["linked_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "issue_id", "policy_id", name="uq_issue_policy_links_org_issue_policy"),
    )
    op.create_index("ix_issue_policy_links_org_issue", "issue_policy_links", ["organization_id", "issue_id"], unique=False)
    op.create_index("ix_issue_policy_links_org_policy", "issue_policy_links", ["organization_id", "policy_id"], unique=False)
    op.create_index(
        "ix_issue_policy_links_org_policy_link_type",
        "issue_policy_links",
        ["organization_id", "policy_id", "link_type"],
        unique=False,
    )

    op.create_table(
        "issue_control_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("control_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("failure_type", sa.String(length=50), nullable=False),
        sa.Column("linked_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "failure_type IN ('control_absent', 'control_failed', 'control_bypassed', 'control_ineffective')",
            name="ck_issue_control_links_failure_type",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["control_id"], ["controls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["linked_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "issue_id", "control_id", name="uq_issue_control_links_org_issue_control"),
    )
    op.create_index("ix_issue_control_links_org_issue", "issue_control_links", ["organization_id", "issue_id"], unique=False)
    op.create_index("ix_issue_control_links_org_control", "issue_control_links", ["organization_id", "control_id"], unique=False)
    op.create_index(
        "ix_issue_control_links_org_control_failure_type",
        "issue_control_links",
        ["organization_id", "control_id", "failure_type"],
        unique=False,
    )
    op.create_index("ix_issue_control_links_control_issue", "issue_control_links", ["control_id", "issue_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_issue_control_links_control_issue", table_name="issue_control_links")
    op.drop_index("ix_issue_control_links_org_control_failure_type", table_name="issue_control_links")
    op.drop_index("ix_issue_control_links_org_control", table_name="issue_control_links")
    op.drop_index("ix_issue_control_links_org_issue", table_name="issue_control_links")
    op.drop_table("issue_control_links")

    op.drop_index("ix_issue_policy_links_org_policy_link_type", table_name="issue_policy_links")
    op.drop_index("ix_issue_policy_links_org_policy", table_name="issue_policy_links")
    op.drop_index("ix_issue_policy_links_org_issue", table_name="issue_policy_links")
    op.drop_table("issue_policy_links")
