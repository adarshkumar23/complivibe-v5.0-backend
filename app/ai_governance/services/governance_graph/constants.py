"""Shared vocabulary for the P2 governance knowledge-graph.

Node/edge type sets are the single source of truth for both the DB
CheckConstraints (migration 0312) and the application-level validation on the
manual-edge endpoint. `trigger_reason` / `validation_status` likewise.
"""

from __future__ import annotations

# 7 node types (satellite src/p2_satellite/schema.py).
NODE_TYPES: frozenset[str] = frozenset(
    {"ai_system", "regulation", "jurisdiction", "data_category", "control_type", "obligation", "risk_tier"}
)

# 8 edge types.
EDGE_TYPES: frozenset[str] = frozenset(
    {
        "system_uses",
        "system_deploys_in",
        "data_triggers",
        "jurisdiction_has",
        "regulation_requires",
        "obligation_needs",
        "system_classified_as",
        "risk_tier_adds",
    }
)

# Terminal node types the "Core Decides" derivation collects.
TERMINAL_NODE_TYPES: frozenset[str] = frozenset({"obligation", "control_type"})

TRIGGER_REASONS: frozenset[str] = frozenset({"event", "scheduled", "on_demand"})
VALIDATION_STATUSES: frozenset[str] = frozenset({"validated", "flagged_mismatch", "self_derived"})

# Watched ai_system fields whose change emits a governance_graph_change_event.
WATCHED_AI_SYSTEM_FIELDS: frozenset[str] = frozenset(
    {"deployment_jurisdiction", "data_categories", "risk_tier"}
)
MANUAL_TRIGGER_REASON = "manual_sync"

CORE_REFERENCE_METHODOLOGY_VERSION = "core-reference-v1.0.0"
SELF_DERIVED_VALIDATION_STATUS = "self_derived"

# SQL fragment helpers for CheckConstraints.
def _sql_in(values: frozenset[str]) -> str:
    return ", ".join(f"'{v}'" for v in sorted(values))


NODE_TYPE_CHECK = f"node_type IN ({_sql_in(NODE_TYPES)})"
EDGE_TYPE_CHECK = f"edge_type IN ({_sql_in(EDGE_TYPES)})"
TRIGGER_REASON_CHECK = f"trigger_reason IN ({_sql_in(TRIGGER_REASONS)})"
VALIDATION_STATUS_CHECK = f"validation_status IN ({_sql_in(VALIDATION_STATUSES)})"
