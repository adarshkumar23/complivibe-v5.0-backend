import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.ai_governance.schemas.governance_graph import ManualEdgeCreateRequest
from app.ai_governance.services.governance_graph import graph_query
from app.ai_governance.services.governance_graph.change_events import emit_manual_change_event
from app.ai_governance.services.governance_graph.repository import create_manual_edge, get_node, resolve_ai_system_node_id
from app.core.deps import get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.services.audit_service import AuditService

router = APIRouter(prefix="/ai-governance/knowledge-graph", tags=["ai-governance-knowledge-graph"])


def _require_ai_system_node(db, org_id: uuid.UUID, ai_system_id: uuid.UUID) -> uuid.UUID:
    node_id = resolve_ai_system_node_id(db, org_id, ai_system_id)
    if node_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "ai_system_not_found", "ai_system_id": str(ai_system_id)})
    return node_id


# F1 -----------------------------------------------------------------------
@router.post("/systems/{ai_system_id}/derive-obligations")
def derive_obligations_on_demand(
    ai_system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("governance_graph:read")),
) -> dict:
    _require_ai_system_node(db, organization.id, ai_system_id)
    try:
        result = graph_query.derive_and_persist_traversal(db, organization.id, ai_system_id, trigger_reason="on_demand")
    except graph_query.UnknownAiSystemError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "ai_system_not_found"})
    AuditService(db).write_audit_log(
        action="governance_graph.on_demand_derivation",
        entity_type="governance_graph_traversal_result",
        organization_id=organization.id,
        actor_user_id=membership.user_id,
        entity_id=uuid.UUID(result["traversal_result_id"]),
        after_json={"ai_system_id": str(ai_system_id), "traversal_result_id": result["traversal_result_id"]},
        metadata_json={"source": "api"},
    )
    db.commit()
    return result


# F2 -----------------------------------------------------------------------
@router.get("/systems/{ai_system_id}/graph")
def get_ai_system_graph(
    ai_system_id: uuid.UUID,
    format: str = Query(default="json"),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("governance_graph:read")),
):
    try:
        subgraph = graph_query.get_subgraph(db, organization.id, ai_system_id)
    except graph_query.UnknownAiSystemError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "ai_system_not_found"})
    if format == "html":
        return Response(content=graph_query.render_subgraph_html(subgraph), media_type="text/html")
    return subgraph


# F3 -----------------------------------------------------------------------
@router.post("/edges", status_code=status.HTTP_201_CREATED)
def create_manual_edge_endpoint(
    payload: ManualEdgeCreateRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("governance_graph:write")),
) -> dict:
    source_id = uuid.UUID(payload.source_node_id)
    target_id = uuid.UUID(payload.target_node_id)
    if get_node(db, organization.id, source_id) is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"error": "unknown_source_node_id", "node_id": payload.source_node_id})
    if get_node(db, organization.id, target_id) is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"error": "unknown_target_node_id", "node_id": payload.target_node_id})
    props = dict(payload.properties or {})
    props["source"] = "manual"
    props["added_by"] = str(membership.user_id)
    try:
        edge = create_manual_edge(db, organization.id, source_id, target_id, payload.edge_type, payload.weight, props)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"error": "invalid_edge_type", "message": str(exc)}) from exc
    AuditService(db).write_audit_log(
        action="governance_graph.manual_edge_added",
        entity_type="governance_graph_edge",
        organization_id=organization.id,
        actor_user_id=membership.user_id,
        entity_id=edge.id,
        after_json={"source_node_id": payload.source_node_id, "target_node_id": payload.target_node_id, "edge_type": payload.edge_type},
        metadata_json={"source": "api"},
    )
    affected = graph_query.find_upstream_ai_systems(db, organization.id, source_id)
    for node_key in affected:
        try:
            emit_manual_change_event(db, organization.id, uuid.UUID(node_key))
        except (ValueError, TypeError):
            continue  # node_key not a real ai_system uuid; skip
    db.commit()
    return {"id": str(edge.id), "edge_type": edge.edge_type, "affected_ai_system_ids": affected}


# F4 -----------------------------------------------------------------------
@router.get("/nodes")
def browse_nodes(
    type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("governance_graph:read")),
) -> dict:
    items, total = graph_query.list_nodes(db, organization.id, node_type=type, page=page, page_size=page_size)
    return graph_query.envelope(items, {"total": total, "page": page, "page_size": page_size})


# F5 -----------------------------------------------------------------------
@router.post("/systems/{ai_system_id}/sync")
def sync_ai_system(
    ai_system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("governance_graph:write")),
) -> dict:
    _require_ai_system_node(db, organization.id, ai_system_id)
    event = emit_manual_change_event(db, organization.id, ai_system_id)
    AuditService(db).write_audit_log(
        action="governance_graph.manual_sync_requested",
        entity_type="governance_graph_change_event",
        organization_id=organization.id,
        actor_user_id=membership.user_id,
        entity_id=event.id,
        after_json={"ai_system_id": str(ai_system_id), "change_event_id": str(event.id)},
        metadata_json={"source": "api"},
    )
    db.commit()
    return {"status": "sync_queued", "ai_system_id": str(ai_system_id), "change_event_id": str(event.id)}


# F6 -----------------------------------------------------------------------
@router.get("/gaps")
def get_coverage_gaps(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("governance_graph:read")),
) -> dict:
    gaps = graph_query.find_coverage_gaps(db, organization.id)
    return graph_query.envelope(gaps)
