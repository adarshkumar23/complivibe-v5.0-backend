"""guardrails and approval envelopes

Revision ID: 0128_guardrails_and_approval_envelopes
Revises: 0127_third_party_model_cards_aibom
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0128_guardrails_and_approval_envelopes"
down_revision: str | None = "0127_third_party_model_cards_aibom"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_policy_guardrails",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("guardrail_type", sa.String(length=50), nullable=False),
        sa.Column("constraint_description", sa.Text(), nullable=False),
        sa.Column("constraint_value", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("violation_action", sa.String(length=20), nullable=False, server_default=sa.text("'alert_only'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "guardrail_type IN ('data_scope', 'user_scope', 'action_scope', 'geographic_scope', 'financial_limit', 'approval_required')",
            name="ck_ai_policy_guardrails_type",
        ),
        sa.CheckConstraint(
            "violation_action IN ('alert_only', 'block_and_alert', 'require_approval')",
            name="ck_ai_policy_guardrails_violation_action",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_policy_guardrails_org_system_active",
        "ai_policy_guardrails",
        ["organization_id", "ai_system_id", "is_active"],
        unique=False,
    )
    op.create_index(
        "ix_ai_policy_guardrails_org_active",
        "ai_policy_guardrails",
        ["organization_id", "is_active"],
        unique=False,
    )

    op.create_table(
        "ai_guardrail_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("guardrail_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=20), nullable=False),
        sa.Column("context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "event_type IN ('check_passed', 'violation_detected', 'blocked')",
            name="ck_ai_guardrail_events_type",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["guardrail_id"], ["ai_policy_guardrails.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_guardrail_events_org_system_created",
        "ai_guardrail_events",
        ["organization_id", "ai_system_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_guardrail_events_org_guardrail_created",
        "ai_guardrail_events",
        ["organization_id", "guardrail_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "ai_approval_envelopes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_system_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transition_from", sa.String(length=50), nullable=False),
        sa.Column("transition_to", sa.String(length=50), nullable=False),
        sa.Column("required_approvers", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("approvals_received", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'expired')",
            name="ck_ai_approval_envelopes_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_approval_envelopes_org_system",
        "ai_approval_envelopes",
        ["organization_id", "ai_system_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_approval_envelopes_org_status",
        "ai_approval_envelopes",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_ai_approval_envelopes_expires_status",
        "ai_approval_envelopes",
        ["expires_at", "status"],
        unique=False,
    )

    op.create_table(
        "ai_envelope_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("envelope_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approver_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(length=10), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "decision IN ('approved', 'rejected')",
            name="ck_ai_envelope_approvals_decision",
        ),
        sa.ForeignKeyConstraint(["envelope_id"], ["ai_approval_envelopes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approver_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("envelope_id", "approver_id", name="uq_ai_envelope_approvals_envelope_approver"),
    )


def downgrade() -> None:
    op.drop_table("ai_envelope_approvals")

    op.drop_index("ix_ai_approval_envelopes_expires_status", table_name="ai_approval_envelopes")
    op.drop_index("ix_ai_approval_envelopes_org_status", table_name="ai_approval_envelopes")
    op.drop_index("ix_ai_approval_envelopes_org_system", table_name="ai_approval_envelopes")
    op.drop_table("ai_approval_envelopes")

    op.drop_index("ix_ai_guardrail_events_org_guardrail_created", table_name="ai_guardrail_events")
    op.drop_index("ix_ai_guardrail_events_org_system_created", table_name="ai_guardrail_events")
    op.drop_table("ai_guardrail_events")

    op.drop_index("ix_ai_policy_guardrails_org_active", table_name="ai_policy_guardrails")
    op.drop_index("ix_ai_policy_guardrails_org_system_active", table_name="ai_policy_guardrails")
    op.drop_table("ai_policy_guardrails")
