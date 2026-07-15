"""add compound_insights + compound_insight_candidates (cross-domain recommendation engine)

Revision ID: 0304_compound_insights
Revises: 0303_domain_events
Create Date: 2026-07-15 12:00:00.000000

Interconnection Phase 3 -- cross-domain compound-exposure recommendation engine.
Deterministic code detects compounding exposures over the Phase 2 entity graph;
`compound_insights` is the persisted, org-scoped output (the code-confirmed
detection is the source of truth; the AI narrative is a best-effort upgrade on
top of an always-present templated narrative). `compound_insight_candidates` is
the lightweight flag queue the Phase 1 event bus writes into (flush-only) so the
APScheduler drain can do the traversal + AI work OUTSIDE the publisher's
transaction.

organization_id is strictly non-nullable on both tables for tenant scoping
(ADR-002). A compound insight is deduplicated by (organization_id, dedup_key)
where dedup_key = sha256(org | pattern_id | sorted matched node type:ids).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0304_compound_insights"
down_revision: str | None = "0303_domain_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "compound_insights",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("pattern_id", sa.String(length=100), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="surfaced"),
        sa.Column("dedup_key", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("templated_narrative", sa.Text(), nullable=False),
        sa.Column("narrative_source", sa.String(length=16), nullable=False, server_default="template"),
        sa.Column("narrative_headline", sa.String(length=300), nullable=True),
        sa.Column("narrative_summary", sa.Text(), nullable=True),
        sa.Column(
            "recommended_actions_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "matched_nodes_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("provider_used", sa.String(length=20), nullable=True),
        sa.Column("used_byo_credentials", sa.Boolean(), nullable=True),
        sa.Column("detection_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("last_detected_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_compound_insights_severity",
        ),
        sa.CheckConstraint(
            "status IN ('surfaced', 'auto_resolved')",
            name="ck_compound_insights_status",
        ),
        sa.CheckConstraint(
            "narrative_source IN ('template', 'ai')",
            name="ck_compound_insights_narrative_source",
        ),
        sa.UniqueConstraint("organization_id", "dedup_key", name="uq_compound_insights_org_dedup"),
    )
    op.create_index("ix_compound_insights_org_status", "compound_insights", ["organization_id", "status"])
    op.create_index("ix_compound_insights_org_pattern", "compound_insights", ["organization_id", "pattern_id"])

    op.create_table(
        "compound_insight_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=True),
        sa.Column("flagged_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_compound_insight_candidates_pending",
        "compound_insight_candidates",
        ["organization_id", "processed_at"],
    )
    op.create_index(
        "ix_compound_insight_candidates_entity",
        "compound_insight_candidates",
        ["organization_id", "entity_type", "entity_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_compound_insight_candidates_entity", table_name="compound_insight_candidates")
    op.drop_index("ix_compound_insight_candidates_pending", table_name="compound_insight_candidates")
    op.drop_table("compound_insight_candidates")
    op.drop_index("ix_compound_insights_org_pattern", table_name="compound_insights")
    op.drop_index("ix_compound_insights_org_status", table_name="compound_insights")
    op.drop_table("compound_insights")
