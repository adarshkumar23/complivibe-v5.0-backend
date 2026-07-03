"""issue policy linking refresh

Revision ID: 0187_issue_policy_linking_refresh
Revises: 0186_policy_templates_risk_links
Create Date: 2026-07-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0187_issue_policy_linking_refresh"
down_revision: str | None = "0186_policy_templates_risk_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("issue_policy_links", sa.Column("link_reason", sa.Text(), nullable=True))
    op.add_column("issue_policy_links", sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'active'")))
    op.add_column("issue_policy_links", sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("issue_policy_links", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("issue_policy_links", sa.Column("unlinked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("issue_policy_links", sa.Column("unlinked_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("issue_policy_links", sa.Column("unlink_reason", sa.Text(), nullable=True))

    op.create_foreign_key(
        "fk_issue_policy_links_created_by",
        "issue_policy_links",
        "users",
        ["created_by"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_issue_policy_links_unlinked_by",
        "issue_policy_links",
        "users",
        ["unlinked_by"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute("UPDATE issue_policy_links SET created_by = linked_by WHERE created_by IS NULL")
    op.execute("UPDATE issue_policy_links SET created_at = linked_at WHERE created_at IS NULL")

    op.drop_constraint("uq_issue_policy_links_org_issue_policy", "issue_policy_links", type_="unique")
    op.create_index(
        "uq_issue_policy_links_issue_policy_active",
        "issue_policy_links",
        ["issue_id", "policy_id"],
        unique=True,
        postgresql_where=sa.text("unlinked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_issue_policy_links_issue_policy_active", table_name="issue_policy_links")
    op.create_unique_constraint(
        "uq_issue_policy_links_org_issue_policy",
        "issue_policy_links",
        ["organization_id", "issue_id", "policy_id"],
    )

    op.drop_constraint("fk_issue_policy_links_unlinked_by", "issue_policy_links", type_="foreignkey")
    op.drop_constraint("fk_issue_policy_links_created_by", "issue_policy_links", type_="foreignkey")
    op.drop_column("issue_policy_links", "unlink_reason")
    op.drop_column("issue_policy_links", "unlinked_by")
    op.drop_column("issue_policy_links", "unlinked_at")
    op.drop_column("issue_policy_links", "created_at")
    op.drop_column("issue_policy_links", "created_by")
    op.drop_column("issue_policy_links", "status")
    op.drop_column("issue_policy_links", "link_reason")
