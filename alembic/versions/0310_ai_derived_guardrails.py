"""add ai_derived_guardrails + ai_guardrail_check_events + ai_guardrail_receipts (patent P3)

Agentic policy derivation (patent P3): automated derivation of machine-enforceable
policy (Rego) from regulatory obligations, with per-obligation provenance, plus
agent-action allow/deny enforcement and cryptographically signed decision receipts.

These are NET-NEW, additive tables in a distinct namespace from the existing
human-authored guardrail feature (migration 0128's ``ai_policy_guardrails`` /
``ai_guardrail_events``, which are left untouched):
  * ``ai_derived_guardrails``     -- obligation-derived, Rego-compiled guardrail
                                     with provenance (source_obligation_ids,
                                     constraint_spec_json) -- patent Claim 1.
  * ``ai_guardrail_check_events`` -- one allow/deny enforcement decision per
                                     agent action + the safe action envelope.
  * ``ai_guardrail_receipts``     -- durable per-(org, ai_system) hash chain of
                                     cryptographically signed decision receipts
                                     (patent Claim 4). Core stores receipts but
                                     never the private signing key.

organization_id is strictly non-nullable on all three (tenant scoping, ADR-002).

Revision ID: 0310_ai_derived_guardrails
Revises: 0309_backfill_read_perm_grants
Create Date: 2026-07-18 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0310_ai_derived_guardrails"
down_revision: str | None = "0309_backfill_read_perm_grants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_derived_guardrails",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("ai_system_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("rego_policy", sa.Text(), nullable=False),
        sa.Column("rego_package", sa.String(length=255), nullable=False),
        sa.Column(
            "source_obligation_ids",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "constraint_spec_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("compiled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_derived_guardrails_org_system_active",
        "ai_derived_guardrails",
        ["organization_id", "ai_system_id", "is_active"],
    )
    op.create_index(
        "ix_ai_derived_guardrails_org_active",
        "ai_derived_guardrails",
        ["organization_id", "is_active"],
    )

    op.create_table(
        "ai_guardrail_check_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("guardrail_id", sa.Uuid(), nullable=False),
        sa.Column("ai_system_id", sa.Uuid(), nullable=True),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "action_envelope_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("receipt_id", sa.String(length=64), nullable=True),
        sa.Column("evaluation_ms", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["guardrail_id"], ["ai_derived_guardrails.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("decision IN ('allow', 'deny')", name="ck_ai_guardrail_check_events_decision"),
    )
    op.create_index(
        "ix_ai_guardrail_check_events_org_system_created",
        "ai_guardrail_check_events",
        ["organization_id", "ai_system_id", "created_at"],
    )
    op.create_index(
        "ix_ai_guardrail_check_events_org_guardrail",
        "ai_guardrail_check_events",
        ["organization_id", "guardrail_id"],
    )

    op.create_table(
        "ai_guardrail_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("ai_system_id", sa.Uuid(), nullable=True),
        sa.Column("guardrail_id", sa.Uuid(), nullable=True),
        sa.Column("check_event_id", sa.Uuid(), nullable=True),
        sa.Column("chain_position", sa.Integer(), nullable=False),
        sa.Column("receipt_id", sa.String(length=64), nullable=False),
        sa.Column("receipt_timestamp", sa.String(length=64), nullable=False),
        sa.Column("envelope_hash", sa.String(length=128), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column(
            "reasons_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("previous_receipt_hash", sa.String(length=128), nullable=True),
        sa.Column("signature", sa.String(length=256), nullable=False),
        sa.Column("receipt_hash", sa.String(length=128), nullable=False),
        sa.Column("public_key_hex", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["guardrail_id"], ["ai_derived_guardrails.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["check_event_id"], ["ai_guardrail_check_events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("decision IN ('allow', 'deny')", name="ck_ai_guardrail_receipts_decision"),
        sa.UniqueConstraint(
            "organization_id", "ai_system_id", "chain_position", name="uq_ai_guardrail_receipts_org_sys_pos"
        ),
    )
    op.create_index(
        "ix_ai_guardrail_receipts_org_sys_pos",
        "ai_guardrail_receipts",
        ["organization_id", "ai_system_id", "chain_position"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_guardrail_receipts_org_sys_pos", table_name="ai_guardrail_receipts")
    op.drop_table("ai_guardrail_receipts")
    op.drop_index("ix_ai_guardrail_check_events_org_guardrail", table_name="ai_guardrail_check_events")
    op.drop_index("ix_ai_guardrail_check_events_org_system_created", table_name="ai_guardrail_check_events")
    op.drop_table("ai_guardrail_check_events")
    op.drop_index("ix_ai_derived_guardrails_org_active", table_name="ai_derived_guardrails")
    op.drop_index("ix_ai_derived_guardrails_org_system_active", table_name="ai_derived_guardrails")
    op.drop_table("ai_derived_guardrails")
