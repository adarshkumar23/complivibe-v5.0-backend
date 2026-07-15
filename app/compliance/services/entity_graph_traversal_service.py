"""Recursive-CTE traversal over the entity-graph edge registry (Step 2).

This is the NEW unifying traversal layer described in ``docs/entity_graph_design.md``
sections 3 and 5. It answers the whole-posture question ("if this vendor breaches,
what across my whole compliance posture is reachable?") as a bounded multi-hop
reachability query from an anchor node, reading the ~26 existing FK-enforced edge
tables through :data:`EDGE_REGISTRY` -- no new edge table, no schema change.

It is Postgres-only (the ``CYCLE`` clause is PostgreSQL 14+). The existing Python
BFS (``risk_graph_service``, ``risk_dependency_service``) is left untouched; this
is an additive path for the deep whole-graph query.

Hard safeguards, all per the design doc:

* **Depth ceiling** (default 4) enforced with ``WHERE depth < :max_depth`` in the
  recursive term.
* **Cycle detection** via the PG14 ``CYCLE ... SET ... USING path`` clause -- required
  because this is a general graph (risk cascade, supply chain, obligation
  equivalence all admit cycles).
* **Fan-out / result cap** with an *explicit* ``truncated`` flag in the response --
  the traversal never silently returns a partial set.
* **Tenant scoping applied in the recursive term itself, at every hop** -- the
  ``all_edges`` CTE that both the anchor term and the recursive term draw from is
  filtered to ``organization_id = :org``, so the recursive join can only ever
  follow same-org edges. A vendor (or any entity) shared across two orgs cannot
  bridge them, because each org owns its own disjoint edge rows and no hop ever
  joins across ``organization_id``. This is the critical security property and is
  proven by an adversarial cross-tenant test.

NOTE (future extension point, deferred per design decision #1): a derived
``graph_edges`` projection table maintained by a bus listener would collapse the
per-spec ``UNION ALL`` into a single indexed scan. It is intentionally NOT built
here -- this step is a real-time read layer only. See design doc section 4.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.compliance.services.entity_graph_registry import (
    EDGE_REGISTRY,
    EdgeSpec,
    validate_registry,
)

DEFAULT_MAX_DEPTH = 4
DEFAULT_MAX_NODES = 5000


@dataclass(frozen=True)
class GraphNode:
    entity_type: str
    entity_id: uuid.UUID
    depth: int
    via_edge_types: list[str]
    reached_via_cycle: bool


@dataclass(frozen=True)
class TraversalResult:
    anchor_type: str
    anchor_id: uuid.UUID
    organization_id: uuid.UUID
    max_depth: int
    max_nodes: int
    nodes: list[GraphNode]          # excludes the anchor
    truncated: bool
    cycle_detected: bool
    depth_reached: int
    edge_specs_used: int

    def reachable_ids(self, entity_type: str) -> list[uuid.UUID]:
        return [n.entity_id for n in self.nodes if n.entity_type == entity_type]


def _one_branch(spec: EdgeSpec, *, src_type: str, src_fk: str, tgt_type: str, tgt_fk: str) -> str:
    """Render one UNION-ALL branch: rows of (org, src, tgt, edge_type) for a spec.

    Identifiers come from the validated registry only. The org filter and the
    FK-not-null guards live in every branch, so the resulting edge set is
    single-tenant and free of null-endpoint (dangling) edges.
    """

    t = spec.table
    where = [
        f"{t}.{spec.org_column} = :org",
        f"{t}.{src_fk} IS NOT NULL",
        f"{t}.{tgt_fk} IS NOT NULL",
    ]
    active = spec.active_filter_sql(t)
    if active:
        where.append(active)
    return (
        f"SELECT {t}.{spec.org_column} AS org_id, "
        f"CAST('{src_type}' AS text) AS source_type, {t}.{src_fk} AS source_id, "
        f"CAST('{tgt_type}' AS text) AS target_type, {t}.{tgt_fk} AS target_id, "
        f"CAST('{spec.edge_type}' AS text) AS edge_type "
        f"FROM {t} AS {t} WHERE " + " AND ".join(where)
    )


def build_all_edges_sql(registry: list[EdgeSpec], *, include_deprecated: bool = True) -> str:
    """UNION ALL of every edge branch. Undirected specs emit a reverse branch too."""

    branches: list[str] = []
    for spec in registry:
        if not include_deprecated and spec.seam_status.value == "deprecated_but_present":
            continue
        branches.append(
            _one_branch(spec, src_type=spec.source_type, src_fk=spec.source_fk,
                        tgt_type=spec.target_type, tgt_fk=spec.target_fk)
        )
        if not spec.directed:
            branches.append(
                _one_branch(spec, src_type=spec.target_type, src_fk=spec.target_fk,
                            tgt_type=spec.source_type, tgt_fk=spec.source_fk)
            )
    return "\n    UNION ALL\n    ".join(branches)


def _build_traversal_sql(all_edges_sql: str) -> str:
    # Tenant scoping: all_edges is bound to :org, and BOTH the anchor term and the
    # recursive term read only from all_edges -- so org isolation holds at every hop,
    # not just the anchor.
    return f"""
WITH RECURSIVE
all_edges AS (
    {all_edges_sql}
),
traverse(entity_type, entity_id, depth, via_edge_type) AS (
    SELECT CAST(:anchor_type AS text), CAST(:anchor_id AS uuid), 0, CAST(NULL AS text)
    UNION ALL
    SELECT e.target_type, e.target_id, t.depth + 1, e.edge_type
    FROM traverse t
    JOIN all_edges e
      ON e.source_type = t.entity_type
     AND e.source_id = t.entity_id
    WHERE t.depth < :max_depth
) CYCLE entity_type, entity_id SET is_cycle USING path
SELECT
    entity_type,
    entity_id,
    min(depth) AS depth,
    array_agg(DISTINCT via_edge_type) FILTER (WHERE via_edge_type IS NOT NULL) AS via_edge_types,
    bool_or(is_cycle) AS reached_via_cycle
FROM traverse
GROUP BY entity_type, entity_id
ORDER BY depth, entity_type, entity_id
LIMIT :fetch_limit
"""


class EntityGraphTraversalService:
    """Real-time recursive-CTE reachability over the existing edge tables."""

    def __init__(self, db: Session, *, registry: list[EdgeSpec] | None = None,
                 validate: bool = False) -> None:
        self.db = db
        self.registry = registry if registry is not None else EDGE_REGISTRY
        if validate:
            validate_registry(self.registry)

    def traverse(
        self,
        *,
        anchor_type: str,
        anchor_id: uuid.UUID,
        organization_id: uuid.UUID,
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_nodes: int = DEFAULT_MAX_NODES,
        include_deprecated: bool = True,
    ) -> TraversalResult:
        if max_depth < 0:
            raise ValueError("max_depth must be >= 0")
        if max_nodes < 1:
            raise ValueError("max_nodes must be >= 1")

        active_specs = [
            s for s in self.registry
            if include_deprecated or s.seam_status.value != "deprecated_but_present"
        ]
        all_edges_sql = build_all_edges_sql(self.registry, include_deprecated=include_deprecated)
        sql = _build_traversal_sql(all_edges_sql)

        # +1 so we can tell "hit the cap" apart from "exactly filled it". The cap
        # counts the anchor row too, hence max_nodes + 1 distinct rows requested,
        # and +1 again as the truncation sentinel.
        fetch_limit = max_nodes + 2
        rows = self.db.execute(
            text(sql),
            {
                "org": organization_id,
                "anchor_type": anchor_type,
                "anchor_id": anchor_id,
                "max_depth": max_depth,
                "fetch_limit": fetch_limit,
            },
        ).all()

        nodes: list[GraphNode] = []
        cycle_detected = False
        depth_reached = 0
        for entity_type, entity_id, depth, via_edge_types, reached_via_cycle in rows:
            if reached_via_cycle:
                cycle_detected = True
            # Skip the anchor itself in the returned node set.
            if entity_type == anchor_type and entity_id == anchor_id:
                continue
            depth_reached = max(depth_reached, depth)
            nodes.append(
                GraphNode(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    depth=depth,
                    via_edge_types=list(via_edge_types or []),
                    reached_via_cycle=bool(reached_via_cycle),
                )
            )

        truncated = len(nodes) > max_nodes
        if truncated:
            nodes = nodes[:max_nodes]
            depth_reached = max((n.depth for n in nodes), default=0)

        return TraversalResult(
            anchor_type=anchor_type,
            anchor_id=anchor_id,
            organization_id=organization_id,
            max_depth=max_depth,
            max_nodes=max_nodes,
            nodes=nodes,
            truncated=truncated,
            cycle_detected=cycle_detected,
            depth_reached=depth_reached,
            edge_specs_used=len(active_specs),
        )
