from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.compliance.schemas.entity_graph import EntityGraphTraverseResponse
from app.compliance.services.entity_graph_registry import NODE_TYPES
from app.compliance.services.entity_graph_traversal_service import (
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_NODES,
    EntityGraphTraversalService,
)
from app.core.deps import get_db, require_permission
from app.models.membership import Membership

router = APIRouter(prefix="/graph", tags=["entity-graph"])


@router.get("/traverse", response_model=EntityGraphTraverseResponse)
def traverse_entity_graph(
    entity_type: str = Query(..., description="Anchor node type (see entity graph registry node types)."),
    entity_id: uuid.UUID = Query(..., description="Anchor node id."),
    max_depth: int = Query(default=DEFAULT_MAX_DEPTH, ge=1, le=8, description="Hop ceiling (default 4)."),
    max_nodes: int = Query(default=DEFAULT_MAX_NODES, ge=1, le=50000, description="Result cap; hitting it sets truncated=true."),
    include_deprecated: bool = Query(
        default=True,
        description="Include deprecated-but-present duplicate seam tables (default true, so no real edge is dropped).",
    ),
    db: Session = Depends(get_db),
    membership: Membership = Depends(require_permission("entity_graph:read")),
) -> EntityGraphTraverseResponse:
    """Multi-hop reachability from an anchor entity across the unified cross-entity graph.

    Org scoping is derived from the authenticated user's membership
    (``membership.organization_id``) -- never a client-supplied organization id -- and
    is enforced at every hop of the recursive traversal, so one org's anchor can never
    reach another org's data even through a shared entity.
    """
    if entity_type not in NODE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown entity_type '{entity_type}'. Known node types: {sorted(NODE_TYPES)}",
        )

    result = EntityGraphTraversalService(db).traverse(
        anchor_type=entity_type,
        anchor_id=entity_id,
        organization_id=membership.organization_id,
        max_depth=max_depth,
        max_nodes=max_nodes,
        include_deprecated=include_deprecated,
    )
    return EntityGraphTraverseResponse.from_result(result)
