"""Core's INDEPENDENT obligation re-derivation ('Core Decides').

Given an ai_system node, walk the org's governance graph to the terminal
obligation / control_type nodes it reaches, up to a max depth, with cycle
detection. Postgres runs the recursive CTE; other dialects (SQLite tests) use a
pure-Python port with identical semantics.

Ported from P2 core-side-patch/reference_traversal_cte.py, hardened for core:
UUID node ids, and org-scoping enforced at EVERY hop (P2's CTE started from one
org's node but did not re-filter org on each join; core's convention -- matching
EntityGraphTraversalService -- is per-hop org enforcement so a mis-parented edge
can never bridge tenants).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.models.governance_graph_edge import GovernanceGraphEdge
from app.models.governance_graph_node import GovernanceGraphNode

# :ai_system_node_id, :org_id, :max_traversal_depth
_REFERENCE_CTE_SQL_POSTGRES = text(
    """
    WITH RECURSIVE obligation_graph AS (
        SELECT e.target_node_id AS target_node_id, n.node_type AS node_type, n.node_key AS node_key,
               ARRAY[e.source_node_id] AS path, 1 AS depth
        FROM governance_graph_edges e
        JOIN governance_graph_nodes n ON n.id = e.target_node_id AND n.organization_id = :org_id
        WHERE e.source_node_id = :ai_system_node_id
          AND e.organization_id = :org_id
          AND e.is_active = true
        UNION ALL
        SELECT e.target_node_id, n.node_type, n.node_key,
               og.path || e.source_node_id, og.depth + 1
        FROM governance_graph_edges e
        JOIN governance_graph_nodes n ON n.id = e.target_node_id AND n.organization_id = :org_id
        JOIN obligation_graph og ON og.target_node_id = e.source_node_id
        WHERE og.depth < :max_traversal_depth
          AND e.organization_id = :org_id
          AND e.is_active = true
          AND NOT (e.target_node_id = ANY(og.path))
    )
    SELECT node_type, node_key FROM obligation_graph
    WHERE node_type IN ('obligation', 'control_type')
    """
).bindparams(bindparam("ai_system_node_id"), bindparam("org_id"), bindparam("max_traversal_depth"))


def derive_obligations_reference(
    session: Session, org_id: uuid.UUID, ai_system_node_id: uuid.UUID, max_traversal_depth: int
) -> dict[str, list[str]]:
    """Return {"derived_obligations": [...], "derived_controls": [...]} sorted+deduped."""
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        rows = session.execute(
            _REFERENCE_CTE_SQL_POSTGRES,
            {"ai_system_node_id": ai_system_node_id, "org_id": org_id, "max_traversal_depth": max_traversal_depth},
        ).all()
        pairs: Sequence[tuple[str, str]] = [(r[0], r[1]) for r in rows]
    else:
        pairs = _derive_pure_python(session, org_id, ai_system_node_id, max_traversal_depth)

    obligations = sorted({key for ntype, key in pairs if ntype == "obligation"})
    controls = sorted({key for ntype, key in pairs if ntype == "control_type"})
    return {"derived_obligations": obligations, "derived_controls": controls}


def _derive_pure_python(session, org_id, ai_system_node_id, max_traversal_depth) -> list[tuple[str, str]]:
    # Load this org's active nodes/edges.
    nodes = {
        n.id: (n.node_type, n.node_key)
        for n in session.query(GovernanceGraphNode).filter(GovernanceGraphNode.organization_id == org_id).all()
    }
    outgoing: dict[uuid.UUID, list[uuid.UUID]] = {}
    for e in (
        session.query(GovernanceGraphEdge)
        .filter(GovernanceGraphEdge.organization_id == org_id, GovernanceGraphEdge.is_active.is_(True))
        .all()
    ):
        outgoing.setdefault(e.source_node_id, []).append(e.target_node_id)

    collected: list[tuple[str, str]] = []
    # stack of (node_id, path_excluding_current, depth)
    stack: list[tuple[uuid.UUID, list[uuid.UUID], int]] = [(ai_system_node_id, [], 0)]
    while stack:
        node_id, path, depth = stack.pop()
        if depth >= max_traversal_depth:
            continue
        for target_id in outgoing.get(node_id, ()):
            if target_id in path:  # cycle guard against the OLD path (matches CTE quirk)
                continue
            meta = nodes.get(target_id)
            if meta is not None and meta[0] in ("obligation", "control_type"):
                collected.append(meta)
            stack.append((target_id, path + [node_id], depth + 1))
    return collected
