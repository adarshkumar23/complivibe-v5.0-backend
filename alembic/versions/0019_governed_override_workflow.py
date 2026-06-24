"""governed override workflow

Revision ID: 0019_governed_override_workflow
Revises: 0018_retention_and_attestation_governance
Create Date: 2026-06-19 01:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0019_governed_override_workflow"
down_revision: Union[str, Sequence[str], None] = "0018_retention_and_attestation_governance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "governance_override_requests",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("override_type", sa.String(length=64), nullable=False),
        sa.Column("target_entity_type", sa.String(length=64), nullable=False),
        sa.Column("target_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_action", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("required_approvals", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("approval_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejection_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("execution_result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["executed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cancelled_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_override_requests_org_status",
        "governance_override_requests",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_override_requests_org_type",
        "governance_override_requests",
        ["organization_id", "override_type"],
        unique=False,
    )
    op.create_index(
        "ix_override_requests_org_target",
        "governance_override_requests",
        ["organization_id", "target_entity_type", "target_entity_id"],
        unique=False,
    )

    op.create_table(
        "governance_override_approvals",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("override_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approver_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["override_request_id"], ["governance_override_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approver_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("override_request_id", "approver_user_id", name="uq_override_approval_once"),
    )
    op.create_index(
        "ix_override_approvals_org_request",
        "governance_override_approvals",
        ["organization_id", "override_request_id"],
        unique=False,
    )

    op.create_table(
        "governance_override_events",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("override_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("details_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["override_request_id"], ["governance_override_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_override_events_org_request",
        "governance_override_events",
        ["organization_id", "override_request_id"],
        unique=False,
    )
    op.create_index(
        "ix_override_events_org_type",
        "governance_override_events",
        ["organization_id", "event_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_override_events_org_type", table_name="governance_override_events")
    op.drop_index("ix_override_events_org_request", table_name="governance_override_events")
    op.drop_table("governance_override_events")

    op.drop_index("ix_override_approvals_org_request", table_name="governance_override_approvals")
    op.drop_table("governance_override_approvals")

    op.drop_index("ix_override_requests_org_target", table_name="governance_override_requests")
    op.drop_index("ix_override_requests_org_type", table_name="governance_override_requests")
    op.drop_index("ix_override_requests_org_status", table_name="governance_override_requests")
    op.drop_table("governance_override_requests")
