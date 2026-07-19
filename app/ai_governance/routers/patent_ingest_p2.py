import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.ai_governance.schemas.governance_graph import (
    BatchObligationDerivationRequest,
    GraphStructureRequest,
    ObligationDerivationRequest,
)
from app.ai_governance.services.governance_graph.ingest_service import GovernanceGraphIngestService
from app.ai_governance.services.governance_graph.scope_deps import require_patent_ingest_scope
from app.core.deps import get_db
from app.core.rate_limiter import rate_limiter
from fastapi import HTTPException

router = APIRouter(prefix="/patent-ingest/p2", tags=["patent-ingest-p2"])


@router.post("/obligation-derivation")
@rate_limiter.limiter.limit("120/minute")
def post_obligation_derivation(
    payload: ObligationDerivationRequest,
    request: Request,
    db: Session = Depends(get_db),
    org_id: uuid.UUID = Depends(require_patent_ingest_scope()),
) -> dict:
    result = GovernanceGraphIngestService(db).process_one_derivation(org_id, None, payload)
    db.commit()
    return result


@router.post("/obligation-derivations/batch")
@rate_limiter.limiter.limit("30/minute")
def post_obligation_derivations_batch(
    payload: BatchObligationDerivationRequest,
    request: Request,
    db: Session = Depends(get_db),
    org_id: uuid.UUID = Depends(require_patent_ingest_scope()),
) -> dict:
    svc = GovernanceGraphIngestService(db)
    results = []
    for item in payload.derivations:
        try:
            result = svc.process_one_derivation(org_id, None, item)
            db.commit()
            results.append({"ai_system_id": item.ai_system_id, "ok": True, "result": result})
        except HTTPException as exc:
            db.rollback()
            results.append(
                {"ai_system_id": item.ai_system_id, "ok": False,
                 "error": {"status_code": exc.status_code, "detail": exc.detail}}
            )
    return {"results": results}


@router.post("/graph-structure")
@rate_limiter.limiter.limit("60/minute")
def post_graph_structure(
    payload: GraphStructureRequest,
    request: Request,
    db: Session = Depends(get_db),
    org_id: uuid.UUID = Depends(require_patent_ingest_scope()),
) -> dict:
    result = GovernanceGraphIngestService(db).process_graph_structure(
        org_id, None, payload.nodes, payload.edges, payload.structure_hash
    )
    db.commit()
    return result
