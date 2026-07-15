from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.compliance.schemas.score_explanation import ScoreChangeExplanationOut, explanation_out
from app.compliance.services.score_explanation_service import (
    ScoreExplanationError,
    ScoreExplanationService,
)
from app.core.deps import get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization

router = APIRouter(tags=["score-explanation"])

_PERM = "score_attribution:read"


@router.get("/scoring/snapshots/{snapshot_type}/explain-change", response_model=ScoreChangeExplanationOut)
def explain_snapshot_change(
    snapshot_type: str,
    from_id: uuid.UUID | None = Query(default=None),
    to_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission(_PERM)),
) -> ScoreChangeExplanationOut:
    try:
        exp = ScoreExplanationService(db).explain_snapshot_change(
            org_id=organization.id, snapshot_type=snapshot_type, from_id=from_id, to_id=to_id
        )
    except ScoreExplanationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return explanation_out(exp)


@router.get("/scoring/entity-risk/{entity_type}/{entity_id}/explain-change", response_model=ScoreChangeExplanationOut)
def explain_entity_risk_change(
    entity_type: str,
    entity_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission(_PERM)),
) -> ScoreChangeExplanationOut:
    try:
        exp = ScoreExplanationService(db).explain_entity_risk_change(
            org_id=organization.id, entity_type=entity_type, entity_id=entity_id
        )
    except ScoreExplanationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return explanation_out(exp)


@router.get("/scoring/board-scorecard/explain-change", response_model=ScoreChangeExplanationOut)
def explain_board_change(
    business_unit_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission(_PERM)),
) -> ScoreChangeExplanationOut:
    try:
        exp = ScoreExplanationService(db).explain_board_change(
            org_id=organization.id, business_unit_id=business_unit_id
        )
    except ScoreExplanationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return explanation_out(exp)
