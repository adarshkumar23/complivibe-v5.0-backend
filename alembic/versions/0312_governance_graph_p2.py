"""add P2 governance knowledge-graph tables (patent P2)

Patent P2 (AI knowledge graph for context-aware governance): a materialized
regulatory knowledge graph used to derive which obligations/controls apply to
an AI system from its jurisdiction, data categories, risk tier and role.

Net-new, additive tables (UUID-native, matching core convention -- P2's repo
used BigInteger PKs / String ai_system_id; converted here):
  * governance_graph_nodes / _edges          -- the graph (+ optional 384-dim
    pgvector embedding on nodes, HNSW index for semantic similarity).
  * governance_graph_traversal_results       -- persisted derivations + core's
    independent re-validation status.
  * governance_graph_change_events           -- hybrid-trigger outbox (was
    unmigrated in P2's core-side-patch).
  * ai_system_obligation_links               -- "Core Decides" write target
    (P2 assumed this pre-existed in core; it did not). link_kind+link_key with
    a UNIQUE constraint enabling atomic ON CONFLICT upserts.
  * patent_scoped_keys                       -- hashed, rotatable scoped API
    keys for the satellite export/ingest endpoints (CarbonAccountingApiKey
    pattern).

organization_id is strictly non-nullable on every table (ADR-002).

Requires the pgvector server extension >= 0.5.0 for the HNSW index (verified
0.6.0 available on the target Postgres). CREATE EXTENSION runs in upgrade().

Revision ID: 0312_governance_graph_p2
Revises: 0311_backfill_ai_guardrail_perms
Create Date: 2026-07-19 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0312_governance_graph_p2"
down_revision: str | None = "0311_backfill_ai_guardrail_perms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _jsonb():
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "governance_graph_nodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("node_type", sa.String(length=64), nullable=False),
        sa.Column("node_key", sa.String(length=255), nullable=False),
        sa.Column("properties", _jsonb(), nullable=False, server_default="{}"),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "node_type IN ('ai_system', 'control_type', 'data_category', 'jurisdiction', "
            "'obligation', 'regulation', 'risk_tier')",
            name="ck_governance_graph_nodes_node_type",
        ),
        sa.UniqueConstraint("organization_id", "node_type", "node_key", name="uq_governance_graph_nodes_org_type_key"),
    )
    op.create_index(
        "ix_governance_graph_nodes_org_node_type", "governance_graph_nodes", ["organization_id", "node_type"]
    )
    # HNSW index for cosine similarity on the embedding (pgvector >= 0.5.0).
    op.create_index(
        "ix_governance_graph_nodes_embedding_hnsw",
        "governance_graph_nodes",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "governance_graph_edges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("source_node_id", sa.Uuid(), nullable=False),
        sa.Column("target_node_id", sa.Uuid(), nullable=False),
        sa.Column("edge_type", sa.String(length=64), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("properties", _jsonb(), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_node_id"], ["governance_graph_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_node_id"], ["governance_graph_nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "edge_type IN ('data_triggers', 'jurisdiction_has', 'obligation_needs', "
            "'regulation_requires', 'risk_tier_adds', 'system_classified_as', "
            "'system_deploys_in', 'system_uses')",
            name="ck_governance_graph_edges_edge_type",
        ),
    )
    op.create_index(
        "ix_governance_graph_edges_org_source", "governance_graph_edges", ["organization_id", "source_node_id"]
    )
    op.create_index(
        "ix_governance_graph_edges_org_edge_type", "governance_graph_edges", ["organization_id", "edge_type"]
    )

    op.create_table(
        "governance_graph_traversal_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("ai_system_id", sa.Uuid(), nullable=False),
        sa.Column("traversal_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("input_context", _jsonb(), nullable=False, server_default="{}"),
        sa.Column("derived_obligations", _jsonb(), nullable=False, server_default="[]"),
        sa.Column("derived_controls", _jsonb(), nullable=False, server_default="[]"),
        sa.Column("graph_path", _jsonb(), nullable=True),
        sa.Column("methodology_version", sa.String(length=32), nullable=False),
        sa.Column("trigger_reason", sa.String(length=16), nullable=False),
        sa.Column("validation_status", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("trigger_reason IN ('event', 'on_demand', 'scheduled')", name="ck_ggtr_trigger_reason"),
        sa.CheckConstraint(
            "validation_status IN ('flagged_mismatch', 'self_derived', 'validated')", name="ck_ggtr_validation_status"
        ),
    )
    op.create_index(
        "ix_ggtr_org_ai_system", "governance_graph_traversal_results", ["organization_id", "ai_system_id"]
    )

    op.create_table(
        "governance_graph_change_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("ai_system_id", sa.Uuid(), nullable=False),
        sa.Column("changed_field", sa.String(length=64), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ggce_org_ai_system", "governance_graph_change_events", ["organization_id", "ai_system_id"])
    op.create_index("ix_ggce_changed_at", "governance_graph_change_events", ["changed_at"])

    op.create_table(
        "ai_system_obligation_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("ai_system_id", sa.Uuid(), nullable=False),
        sa.Column("link_kind", sa.String(length=16), nullable=False),
        sa.Column("link_key", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_system_id"], ["ai_systems.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("link_kind IN ('control_type', 'obligation')", name="ck_ai_system_obligation_links_kind"),
        sa.UniqueConstraint(
            "organization_id", "ai_system_id", "link_kind", "link_key", name="uq_ai_sys_obl_links_org_sys_kind_key"
        ),
    )
    op.create_index("ix_ai_sys_obl_links_org_sys", "ai_system_obligation_links", ["organization_id", "ai_system_id"])

    op.create_table(
        "patent_scoped_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("key_type", sa.String(length=16), nullable=False),
        sa.Column("api_key_hash", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("key_type IN ('export', 'ingest')", name="ck_patent_scoped_keys_key_type"),
        sa.UniqueConstraint("organization_id", "key_type", name="uq_patent_scoped_keys_org_type"),
    )


def downgrade() -> None:
    op.drop_table("patent_scoped_keys")
    op.drop_index("ix_ai_sys_obl_links_org_sys", table_name="ai_system_obligation_links")
    op.drop_table("ai_system_obligation_links")
    op.drop_index("ix_ggce_changed_at", table_name="governance_graph_change_events")
    op.drop_index("ix_ggce_org_ai_system", table_name="governance_graph_change_events")
    op.drop_table("governance_graph_change_events")
    op.drop_index("ix_ggtr_org_ai_system", table_name="governance_graph_traversal_results")
    op.drop_table("governance_graph_traversal_results")
    op.drop_index("ix_governance_graph_edges_org_edge_type", table_name="governance_graph_edges")
    op.drop_index("ix_governance_graph_edges_org_source", table_name="governance_graph_edges")
    op.drop_table("governance_graph_edges")
    op.drop_index("ix_governance_graph_nodes_embedding_hnsw", table_name="governance_graph_nodes")
    op.drop_index("ix_governance_graph_nodes_org_node_type", table_name="governance_graph_nodes")
    op.drop_table("governance_graph_nodes")
