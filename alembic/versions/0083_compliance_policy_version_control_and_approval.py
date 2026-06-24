"""compliance policy version control and approval

Revision ID: 0083_compliance_policy_version_control_and_approval
Revises: 0082_compliance_policy_management_foundation
Create Date: 2026-06-22 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0083_compliance_policy_version_control_and_approval"
down_revision: str | None = "0082_compliance_policy_management_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "compliance_policy_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.String(length=32), nullable=False),
        sa.Column("content_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("submitted_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_id"], ["compliance_policies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["submitted_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_compliance_policy_versions_organization_id",
        "compliance_policy_versions",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_compliance_policy_versions_org_policy",
        "compliance_policy_versions",
        ["organization_id", "policy_id"],
        unique=False,
    )
    op.create_index(
        "ix_compliance_policy_versions_org_status",
        "compliance_policy_versions",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_compliance_policy_versions_org_created",
        "compliance_policy_versions",
        ["organization_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "compliance_policy_approval_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approver_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_id"], ["compliance_policies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["compliance_policy_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approver_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_compliance_policy_approval_requests_organization_id",
        "compliance_policy_approval_requests",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_compliance_policy_approval_requests_org_policy",
        "compliance_policy_approval_requests",
        ["organization_id", "policy_id"],
        unique=False,
    )
    op.create_index(
        "ix_compliance_policy_approval_requests_org_version",
        "compliance_policy_approval_requests",
        ["organization_id", "version_id"],
        unique=False,
    )
    op.create_index(
        "ix_compliance_policy_approval_requests_org_status",
        "compliance_policy_approval_requests",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_compliance_policy_approval_requests_org_created",
        "compliance_policy_approval_requests",
        ["organization_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_compliance_policy_approval_requests_org_created",
        table_name="compliance_policy_approval_requests",
    )
    op.drop_index(
        "ix_compliance_policy_approval_requests_org_status",
        table_name="compliance_policy_approval_requests",
    )
    op.drop_index(
        "ix_compliance_policy_approval_requests_org_version",
        table_name="compliance_policy_approval_requests",
    )
    op.drop_index(
        "ix_compliance_policy_approval_requests_org_policy",
        table_name="compliance_policy_approval_requests",
    )
    op.drop_index(
        "ix_compliance_policy_approval_requests_organization_id",
        table_name="compliance_policy_approval_requests",
    )
    op.drop_table("compliance_policy_approval_requests")

    op.drop_index("ix_compliance_policy_versions_org_created", table_name="compliance_policy_versions")
    op.drop_index("ix_compliance_policy_versions_org_status", table_name="compliance_policy_versions")
    op.drop_index("ix_compliance_policy_versions_org_policy", table_name="compliance_policy_versions")
    op.drop_index("ix_compliance_policy_versions_organization_id", table_name="compliance_policy_versions")
    op.drop_table("compliance_policy_versions")
