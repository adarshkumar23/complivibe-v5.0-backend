"""ai system governance guardrails freeze windows and operator acknowledgements

Revision ID: 0043_ai_system_governance_guardrails
Revises: 0042_ai_system_governance_sequence_packs
Create Date: 2026-06-19 22:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0043_ai_system_governance_guardrails"
down_revision: str | None = "0042_ai_system_governance_sequence_packs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_system_governance_freeze_windows",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("scope_json", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["archived_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_governance_freeze_windows_organization_id",
        "ai_system_governance_freeze_windows",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_freeze_windows_org_status",
        "ai_system_governance_freeze_windows",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_freeze_windows_org_scope",
        "ai_system_governance_freeze_windows",
        ["organization_id", "scope_type"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_freeze_windows_org_window",
        "ai_system_governance_freeze_windows",
        ["organization_id", "starts_at", "ends_at"],
        unique=False,
    )

    op.create_table(
        "ai_system_governance_operator_acknowledgements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("acknowledgement_text", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("override_freeze", sa.Boolean(), nullable=False),
        sa.Column("freeze_window_ids_json", sa.JSON(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_system_governance_operator_acknowledgements_organization_id",
        "ai_system_governance_operator_acknowledgements",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_op_ack_org_action",
        "ai_system_governance_operator_acknowledgements",
        ["organization_id", "action_type"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_op_ack_org_target",
        "ai_system_governance_operator_acknowledgements",
        ["organization_id", "target_type", "target_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_sys_gov_op_ack_org_created",
        "ai_system_governance_operator_acknowledgements",
        ["organization_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_sys_gov_op_ack_org_created",
        table_name="ai_system_governance_operator_acknowledgements",
    )
    op.drop_index(
        "ix_ai_sys_gov_op_ack_org_target",
        table_name="ai_system_governance_operator_acknowledgements",
    )
    op.drop_index(
        "ix_ai_sys_gov_op_ack_org_action",
        table_name="ai_system_governance_operator_acknowledgements",
    )
    op.drop_index(
        "ix_ai_system_governance_operator_acknowledgements_organization_id",
        table_name="ai_system_governance_operator_acknowledgements",
    )
    op.drop_table("ai_system_governance_operator_acknowledgements")

    op.drop_index("ix_ai_sys_gov_freeze_windows_org_window", table_name="ai_system_governance_freeze_windows")
    op.drop_index("ix_ai_sys_gov_freeze_windows_org_scope", table_name="ai_system_governance_freeze_windows")
    op.drop_index("ix_ai_sys_gov_freeze_windows_org_status", table_name="ai_system_governance_freeze_windows")
    op.drop_index(
        "ix_ai_system_governance_freeze_windows_organization_id",
        table_name="ai_system_governance_freeze_windows",
    )
    op.drop_table("ai_system_governance_freeze_windows")
