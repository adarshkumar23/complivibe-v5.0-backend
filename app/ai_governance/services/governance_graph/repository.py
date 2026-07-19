"""Query/write helpers over the governance-graph tables (UUID-native).

Ported from P2 core-side-patch/models.py's function layer. Key change beyond
UUID: `upsert_ai_system_obligation_links` is now atomic and concurrency-safe --
`INSERT ... ON CONFLICT DO NOTHING` on the unique (org, ai_system, link_kind,
link_key) constraint -- replacing P2's non-atomic query-then-insert (two
concurrent derivations for the same system could both read a stale 'existing'
set and double-insert).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.ai_governance.services.governance_graph.constants import EDGE_TYPES
from app.models.ai_system_obligation_link import AiSystemObligationLink
from app.models.governance_graph_edge import GovernanceGraphEdge
from app.models.governance_graph_node import GovernanceGraphNode


def load_active_catalog(session: Session, org_id: uuid.UUID) -> dict[str, set[str]]:
    """The org's live catalog: active obligation + control_type node keys."""
    rows = session.execute(
        select(GovernanceGraphNode.node_type, GovernanceGraphNode.node_key).where(
            GovernanceGraphNode.organization_id == org_id,
            GovernanceGraphNode.archived.is_(False),
            GovernanceGraphNode.node_type.in_(["obligation", "control_type"]),
        )
    ).all()
    catalog: dict[str, set[str]] = {"obligation": set(), "control_type": set()}
    for node_type, node_key in rows:
        catalog[node_type].add(node_key)
    return catalog


def get_node(session: Session, org_id: uuid.UUID, node_id: uuid.UUID) -> GovernanceGraphNode | None:
    return session.execute(
        select(GovernanceGraphNode).where(
            GovernanceGraphNode.organization_id == org_id,
            GovernanceGraphNode.id == node_id,
            GovernanceGraphNode.archived.is_(False),
        )
    ).scalar_one_or_none()


def get_node_by_natural_key(
    session: Session, org_id: uuid.UUID, node_type: str, node_key: str
) -> GovernanceGraphNode | None:
    return session.execute(
        select(GovernanceGraphNode).where(
            GovernanceGraphNode.organization_id == org_id,
            GovernanceGraphNode.node_type == node_type,
            GovernanceGraphNode.node_key == node_key,
        )
    ).scalar_one_or_none()


def resolve_ai_system_node_id(
    session: Session, org_id: uuid.UUID, ai_system_id: uuid.UUID
) -> uuid.UUID | None:
    node = get_node_by_natural_key(session, org_id, "ai_system", str(ai_system_id))
    return node.id if node is not None else None


def create_manual_edge(
    session: Session,
    org_id: uuid.UUID,
    source_node_id: uuid.UUID,
    target_node_id: uuid.UUID,
    edge_type: str,
    weight: float,
    properties: dict,
) -> GovernanceGraphEdge:
    if edge_type not in EDGE_TYPES:
        raise ValueError(f"unknown edge_type {edge_type!r}; allowed: {sorted(EDGE_TYPES)}")
    edge = GovernanceGraphEdge(
        organization_id=org_id,
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        edge_type=edge_type,
        weight=weight,
        properties=properties or {},
        is_active=True,
    )
    session.add(edge)
    session.flush()
    return edge


def upsert_graph_structure(
    session: Session, org_id: uuid.UUID, nodes: Iterable, edges: Iterable
) -> dict[str, int]:
    """Upsert a batch of nodes (by org+type+key) and edges (by org+source+target+
    edge_type). Nodes are duck-typed on .node_type/.node_key/.properties; edges
    on .source_node_type/.source_node_key/.target_node_type/.target_node_key/
    .edge_type/.is_active/.weight/.properties.
    """
    counts = {"nodes_created": 0, "nodes_updated": 0, "edges_created": 0, "edges_updated": 0}

    for n in nodes:
        existing = get_node_by_natural_key(session, org_id, n.node_type, n.node_key)
        if existing is None:
            session.add(
                GovernanceGraphNode(
                    organization_id=org_id,
                    node_type=n.node_type,
                    node_key=n.node_key,
                    properties=dict(getattr(n, "properties", {}) or {}),
                )
            )
            counts["nodes_created"] += 1
        else:
            existing.properties = dict(getattr(n, "properties", {}) or {})
            counts["nodes_updated"] += 1
    session.flush()

    for e in edges:
        src = get_node_by_natural_key(session, org_id, e.source_node_type, e.source_node_key)
        tgt = get_node_by_natural_key(session, org_id, e.target_node_type, e.target_node_key)
        if src is None or tgt is None:
            # Skip edges referencing nodes not present in this org (defensive).
            continue
        if e.edge_type not in EDGE_TYPES:
            raise ValueError(f"unknown edge_type {e.edge_type!r}")
        existing_edge = session.execute(
            select(GovernanceGraphEdge).where(
                GovernanceGraphEdge.organization_id == org_id,
                GovernanceGraphEdge.source_node_id == src.id,
                GovernanceGraphEdge.target_node_id == tgt.id,
                GovernanceGraphEdge.edge_type == e.edge_type,
            )
        ).scalar_one_or_none()
        if existing_edge is None:
            session.add(
                GovernanceGraphEdge(
                    organization_id=org_id,
                    source_node_id=src.id,
                    target_node_id=tgt.id,
                    edge_type=e.edge_type,
                    weight=getattr(e, "weight", 1.0),
                    properties=dict(getattr(e, "properties", {}) or {}),
                    is_active=getattr(e, "is_active", True),
                )
            )
            counts["edges_created"] += 1
        else:
            existing_edge.is_active = getattr(e, "is_active", True)
            existing_edge.weight = getattr(e, "weight", 1.0)
            existing_edge.properties = dict(getattr(e, "properties", {}) or {})
            counts["edges_updated"] += 1
    session.flush()
    return counts


def upsert_ai_system_obligation_links(
    session: Session,
    org_id: uuid.UUID,
    ai_system_id: uuid.UUID,
    derived_obligations: list[str],
    derived_controls: list[str],
) -> int:
    """Atomically upsert validated obligation/control links for one AI system.

    Uses INSERT ... ON CONFLICT DO NOTHING against
    uq_ai_sys_obl_links_org_sys_kind_key, so concurrent derivations for the same
    (org, ai_system) can't produce duplicates. Returns the number of rows
    actually inserted (new links).
    """
    values = [
        {"id": uuid.uuid4(), "organization_id": org_id, "ai_system_id": ai_system_id, "link_kind": "obligation", "link_key": k}
        for k in dict.fromkeys(derived_obligations)
    ] + [
        {"id": uuid.uuid4(), "organization_id": org_id, "ai_system_id": ai_system_id, "link_kind": "control_type", "link_key": k}
        for k in dict.fromkeys(derived_controls)
    ]
    if not values:
        return 0
    stmt = (
        pg_insert(AiSystemObligationLink)
        .values(values)
        .on_conflict_do_nothing(constraint="uq_ai_sys_obl_links_org_sys_kind_key")
    )
    result = session.execute(stmt)
    return result.rowcount or 0
