"""Read/derive query layer behind the human knowledge-graph endpoints.

Pure (no FastAPI). UUID-native, org-scoped. Ported from P2
core-side-patch/graph_query.py. pyvis is imported function-locally inside
render_subgraph_html so it stays an OPTIONAL dependency (only needed for the
?format=html debug view; the JSON contract never touches it).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_governance.services.governance_graph.constants import (
    CORE_REFERENCE_METHODOLOGY_VERSION,
    SELF_DERIVED_VALIDATION_STATUS,
)
from app.ai_governance.services.governance_graph.reference_cte import derive_obligations_reference
from app.ai_governance.services.governance_graph.repository import (
    resolve_ai_system_node_id,
    upsert_ai_system_obligation_links,
)
from app.core.config import get_settings
from app.models.governance_graph_edge import GovernanceGraphEdge
from app.models.governance_graph_node import GovernanceGraphNode
from app.models.governance_graph_traversal_result import GovernanceGraphTraversalResult


class UnknownAiSystemError(ValueError):
    pass


def resolve_max_traversal_depth() -> int:
    return get_settings().GOVERNANCE_GRAPH_MAX_TRAVERSAL_DEPTH


def derive_and_persist_traversal(
    session: Session,
    org_id: uuid.UUID,
    ai_system_id: uuid.UUID,
    trigger_reason: str,
    *,
    persist_links: bool = True,
) -> dict:
    """Run core's own reference derivation for an AI system, persist a
    self-derived traversal result, and (optionally) upsert the obligation links.
    """
    node_id = resolve_ai_system_node_id(session, org_id, ai_system_id)
    if node_id is None:
        raise UnknownAiSystemError(str(ai_system_id))

    derived = derive_obligations_reference(session, org_id, node_id, resolve_max_traversal_depth())
    result = GovernanceGraphTraversalResult(
        organization_id=org_id,
        ai_system_id=ai_system_id,
        input_context={"trigger_reason": trigger_reason},
        derived_obligations=derived["derived_obligations"],
        derived_controls=derived["derived_controls"],
        graph_path=None,
        methodology_version=CORE_REFERENCE_METHODOLOGY_VERSION,
        trigger_reason=trigger_reason if trigger_reason in ("event", "scheduled", "on_demand") else "on_demand",
        validation_status=SELF_DERIVED_VALIDATION_STATUS,
    )
    session.add(result)
    session.flush()
    if persist_links:
        upsert_ai_system_obligation_links(
            session, org_id, ai_system_id, derived["derived_obligations"], derived["derived_controls"]
        )
    return {
        "traversal_result_id": str(result.id),
        "ai_system_id": str(ai_system_id),
        "derived_obligations": derived["derived_obligations"],
        "derived_controls": derived["derived_controls"],
        "validation_status": result.validation_status,
        "traversal_at": datetime.now(UTC).isoformat(),
    }


def get_subgraph(session: Session, org_id: uuid.UUID, ai_system_id: uuid.UUID, max_depth: int | None = None) -> dict:
    """Forward BFS from an ai_system node, returning {nodes, edges} for display."""
    node_id = resolve_ai_system_node_id(session, org_id, ai_system_id)
    if node_id is None:
        raise UnknownAiSystemError(str(ai_system_id))
    max_depth = max_depth or resolve_max_traversal_depth()

    node_rows = {
        n.id: n
        for n in session.query(GovernanceGraphNode).filter(GovernanceGraphNode.organization_id == org_id).all()
    }
    outgoing: dict[uuid.UUID, list] = {}
    for e in (
        session.query(GovernanceGraphEdge)
        .filter(GovernanceGraphEdge.organization_id == org_id, GovernanceGraphEdge.is_active.is_(True))
        .all()
    ):
        outgoing.setdefault(e.source_node_id, []).append(e)

    seen_nodes: set[uuid.UUID] = {node_id}
    seen_edges: list = []
    frontier = [(node_id, 0)]
    while frontier:
        nid, depth = frontier.pop()
        if depth >= max_depth:
            continue
        for e in outgoing.get(nid, ()):
            seen_edges.append(e)
            if e.target_node_id not in seen_nodes:
                seen_nodes.add(e.target_node_id)
                frontier.append((e.target_node_id, depth + 1))

    nodes = [
        {"id": str(nid), "type": node_rows[nid].node_type, "label": node_rows[nid].node_key,
         "properties": node_rows[nid].properties}
        for nid in seen_nodes
        if nid in node_rows
    ]
    edges = [
        {"source": str(e.source_node_id), "target": str(e.target_node_id), "type": e.edge_type}
        for e in seen_edges
    ]
    return {"nodes": nodes, "edges": edges}


def find_upstream_ai_systems(
    session: Session, org_id: uuid.UUID, node_id: uuid.UUID, max_depth: int | None = None
) -> list[str]:
    """Reverse BFS from a node to the ai_system node_keys that reach it."""
    max_depth = max_depth or resolve_max_traversal_depth()
    incoming: dict[uuid.UUID, list[uuid.UUID]] = {}
    for e in (
        session.query(GovernanceGraphEdge)
        .filter(GovernanceGraphEdge.organization_id == org_id, GovernanceGraphEdge.is_active.is_(True))
        .all()
    ):
        incoming.setdefault(e.target_node_id, []).append(e.source_node_id)
    node_types = {
        n.id: (n.node_type, n.node_key)
        for n in session.query(GovernanceGraphNode).filter(GovernanceGraphNode.organization_id == org_id).all()
    }

    found: set[str] = set()
    seen: set[uuid.UUID] = {node_id}
    frontier = [(node_id, 0)]
    while frontier:
        nid, depth = frontier.pop()
        if depth >= max_depth:
            continue
        for src in incoming.get(nid, ()):
            meta = node_types.get(src)
            if meta and meta[0] == "ai_system":
                found.add(meta[1])
            if src not in seen:
                seen.add(src)
                frontier.append((src, depth + 1))
    return sorted(found)


def list_nodes(
    session: Session, org_id: uuid.UUID, node_type: str | None = None, page: int = 1, page_size: int = 50
) -> tuple[list[dict], int]:
    stmt = select(GovernanceGraphNode).where(GovernanceGraphNode.organization_id == org_id)
    count_stmt = select(GovernanceGraphNode).where(GovernanceGraphNode.organization_id == org_id)
    if node_type is not None:
        stmt = stmt.where(GovernanceGraphNode.node_type == node_type)
        count_stmt = count_stmt.where(GovernanceGraphNode.node_type == node_type)
    total = len(session.execute(count_stmt).scalars().all())
    rows = session.execute(
        stmt.order_by(GovernanceGraphNode.node_type, GovernanceGraphNode.node_key)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).scalars().all()
    items = [{"id": str(n.id), "type": n.node_type, "key": n.node_key, "properties": n.properties} for n in rows]
    return items, total


def find_coverage_gaps(session: Session, org_id: uuid.UUID) -> list[dict]:
    """Obligations that require a control (obligation_needs edge) whose target
    control_type has no incoming satisfying edge in the org's graph -- i.e.
    obligations with an unmet control need."""
    nodes = {
        n.id: (n.node_type, n.node_key)
        for n in session.query(GovernanceGraphNode).filter(GovernanceGraphNode.organization_id == org_id).all()
    }
    edges = (
        session.query(GovernanceGraphEdge)
        .filter(GovernanceGraphEdge.organization_id == org_id, GovernanceGraphEdge.is_active.is_(True))
        .all()
    )
    needs = [(e.source_node_id, e.target_node_id) for e in edges if e.edge_type == "obligation_needs"]
    satisfied_targets = {e.target_node_id for e in edges if e.edge_type in ("system_uses",)}
    gaps: list[dict] = []
    for obl_id, ctrl_id in needs:
        if ctrl_id not in satisfied_targets:
            obl = nodes.get(obl_id)
            ctrl = nodes.get(ctrl_id)
            if obl:
                gaps.append(
                    {"obligation": obl[1], "missing_control": ctrl[1] if ctrl else None}
                )
    return gaps


def envelope(items, meta_extra: dict | None = None) -> dict:
    meta = {"count": len(items)}
    if meta_extra:
        meta.update(meta_extra)
    return {"items": items, "meta": meta}


def render_subgraph_html(subgraph: dict) -> str:
    """Optional HTML rendering via pyvis (imported here so pyvis is only needed
    when ?format=html is actually requested)."""
    try:
        from pyvis.network import Network
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("pyvis is not installed; the ?format=html view is unavailable") from exc

    net = Network(directed=True, cdn_resources="in_line")
    for node in subgraph["nodes"]:
        net.add_node(node["id"], label=node["label"], title=node["type"])
    for edge in subgraph["edges"]:
        net.add_edge(edge["source"], edge["target"], title=edge["type"])
    return net.generate_html()
