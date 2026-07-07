import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.compliance.services.entity_risk_score_service import EntityRiskScoreService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.entity_risk_score import EntityRiskScore
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.entity_risk_score import (
    EntityRiskScoreComputeRequest,
    EntityRiskScoreRead,
    EntityRiskScoreSummaryItem,
    EntityRiskScoreSummaryResponse,
    EntityRiskScoreTypeSummary,
    EntityRiskScoreByBand,
)

router = APIRouter(prefix="/compliance/risk-scores", tags=["risk-scores"])

ALL_ENTITY_TYPES = ["vendor", "framework", "asset", "data_asset", "business_unit"]


def _as_read(row: EntityRiskScore, *, stale: bool = False, stale_reasons: list[str] | None = None) -> EntityRiskScoreRead:
    return EntityRiskScoreRead(
        id=row.id,
        organization_id=row.organization_id,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        entity_label=row.entity_label,
        composite_score=float(row.composite_score),
        score_band=row.score_band,
        risk_count=row.risk_count,
        score_method=row.score_method,
        component_risks_json=row.component_risks_json if isinstance(row.component_risks_json, list) else [],
        computation_notes=row.computation_notes,
        computed_by_user_id=row.computed_by_user_id,
        computed_at=row.computed_at,
        created_at=row.created_at,
        stale=stale,
        stale_reasons=stale_reasons or [],
    )


def _band_counts(rows: list[EntityRiskScore]) -> EntityRiskScoreByBand:
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "none": 0}
    for row in rows:
        if row.score_band in counts:
            counts[row.score_band] += 1
    return EntityRiskScoreByBand(**counts)


@router.post("/compute-entity", response_model=EntityRiskScoreRead, status_code=status.HTTP_201_CREATED)
def compute_entity_score(
    payload: EntityRiskScoreComputeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risks:write")),
) -> EntityRiskScoreRead:
    row = EntityRiskScoreService.compute(
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        org_id=organization.id,
        score_method=payload.score_method,
        computed_by_user_id=current_user.id,
        db=db,
    )
    db.commit()
    db.refresh(row)
    return _as_read(row)


@router.get("/summary", response_model=EntityRiskScoreSummaryResponse)
def get_entity_score_summary(
    entity_type: str | None = Query(default=None, pattern="^(vendor|asset|data_asset|business_unit|framework)$"),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risks:read")),
) -> EntityRiskScoreSummaryResponse:
    target_types = [entity_type] if entity_type else ALL_ENTITY_TYPES

    by_entity_type: dict[str, EntityRiskScoreTypeSummary] = {}
    highest_candidates: list[EntityRiskScore] = []

    for et in target_types:
        latest_rows = EntityRiskScoreService.get_all_latest(et, organization.id, db)
        avg = round(sum(float(row.composite_score) for row in latest_rows) / len(latest_rows), 2) if latest_rows else 0.0
        last_computed_at = max((row.computed_at for row in latest_rows), default=None)

        by_entity_type[et] = EntityRiskScoreTypeSummary(
            total_scored=len(latest_rows),
            by_band=_band_counts(latest_rows),
            avg_composite_score=avg,
            last_computed_at=last_computed_at,
        )
        highest_candidates.extend(latest_rows)

    top_five = sorted(highest_candidates, key=lambda row: (float(row.composite_score), row.computed_at), reverse=True)[:5]
    highest_risk_entities = [
        EntityRiskScoreSummaryItem(
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            entity_label=row.entity_label,
            composite_score=float(row.composite_score),
            score_band=row.score_band,
            computed_at=row.computed_at,
        )
        for row in top_five
    ]

    return EntityRiskScoreSummaryResponse(by_entity_type=by_entity_type, highest_risk_entities=highest_risk_entities)


@router.get("/by-entity", response_model=EntityRiskScoreRead | list[EntityRiskScoreRead])
def get_scores_by_entity(
    entity_type: str = Query(pattern="^(vendor|asset|data_asset|business_unit|framework)$"),
    entity_id: uuid.UUID = Query(),
    include_history: bool = Query(default=False),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risks:read")),
) -> EntityRiskScoreRead | list[EntityRiskScoreRead]:
    if include_history:
        rows = EntityRiskScoreService.get_history(entity_type, entity_id, organization.id, db, limit=10)
        if not rows:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity risk score not found")
        # Only the most recent snapshot's currency is meaningful to flag -- older history rows
        # are expected to differ from current state by definition.
        results = []
        for i, row in enumerate(rows):
            if i == 0:
                stale, reasons = EntityRiskScoreService.staleness(row, organization.id, db)
                results.append(_as_read(row, stale=stale, stale_reasons=reasons))
            else:
                results.append(_as_read(row))
        return results

    row = EntityRiskScoreService.get_latest(entity_type, entity_id, organization.id, db)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity risk score not found")
    stale, reasons = EntityRiskScoreService.staleness(row, organization.id, db)
    return _as_read(row, stale=stale, stale_reasons=reasons)
