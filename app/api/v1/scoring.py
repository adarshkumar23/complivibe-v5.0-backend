from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.score_snapshot import ScoreSnapshot
from app.models.user import User
from app.schemas.scoring import (
    ScoreDeltaResponse,
    ScoreLatestResponse,
    ScoreListResponse,
    ScoreMethodologyResponse,
    ScoreSnapshotMaterializeRequest,
    ScoreSnapshotMaterializeResponse,
    ScoreSnapshotRead,
    ScoreTrendsResponse,
    ScoreSummary,
)
from app.services.audit_service import AuditService
from app.services.scoring_service import SNAPSHOT_TYPES, ScoringService

router = APIRouter(prefix="/scoring", tags=["scoring"])


def _snapshot_read(row: ScoreSnapshot) -> ScoreSnapshotRead:
    return ScoreSnapshotRead(
        id=row.id,
        organization_id=row.organization_id,
        snapshot_type=row.snapshot_type,
        score=row.score,
        grade=row.grade,
        inputs_json=row.inputs_json,
        breakdown_json=row.breakdown_json,
        recommendations_json=row.recommendations_json,
        calculated_at=row.calculated_at,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/summary", response_model=ScoreSummary)
def scoring_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("dashboard:read")),
) -> ScoreSummary:
    latest = ScoringService(db).latest_snapshots(organization.id)
    governance = next((row for row in latest if row.snapshot_type == "governance_health"), None)
    if governance is None:
        return ScoreSummary(score=0, captured_at=ScoringService.now())
    return ScoreSummary(score=governance.score, captured_at=governance.calculated_at)


@router.post("/snapshots/materialize", response_model=ScoreSnapshotMaterializeResponse)
def materialize_score_snapshots(
    payload: ScoreSnapshotMaterializeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("dashboard:read")),
) -> ScoreSnapshotMaterializeResponse:
    if payload.snapshot_types:
        unknown = [item for item in payload.snapshot_types if item not in SNAPSHOT_TYPES]
        if unknown:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported snapshot_type(s): {', '.join(unknown)}")

    service = ScoringService(db)
    rows = service.materialize_snapshots(
        organization_id=organization.id,
        snapshot_types=payload.snapshot_types,
        dry_run=payload.dry_run,
        created_by_user_id=current_user.id,
    )

    AuditService(db).write_audit_log(
        action="score_snapshot.materialized",
        entity_type="score_snapshot",
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "dry_run": payload.dry_run,
            "snapshot_types": [row.snapshot_type for row in rows],
            "count": len(rows),
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    if not payload.dry_run:
        db.commit()
    else:
        db.flush()

    return ScoreSnapshotMaterializeResponse(
        dry_run=payload.dry_run,
        snapshots=[_snapshot_read(row) for row in rows],
    )


@router.get("/snapshots/latest", response_model=ScoreLatestResponse)
def latest_score_snapshots(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("dashboard:read")),
) -> ScoreLatestResponse:
    rows = ScoringService(db).latest_snapshots(organization.id)
    return ScoreLatestResponse(snapshots=[_snapshot_read(row) for row in rows])


@router.get("/snapshots", response_model=ScoreListResponse)
def list_score_snapshots(
    snapshot_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("dashboard:read")),
) -> ScoreListResponse:
    if snapshot_type is not None and snapshot_type not in SNAPSHOT_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported snapshot_type")

    rows = ScoringService(db).list_snapshots(
        organization.id,
        snapshot_type=snapshot_type,
        limit=limit,
        offset=offset,
    )
    return ScoreListResponse(snapshots=[_snapshot_read(row) for row in rows])


@router.get("/snapshots/trends", response_model=ScoreTrendsResponse)
def score_snapshot_trends(
    snapshot_type: str | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=3650),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("dashboard:read")),
) -> ScoreTrendsResponse:
    if snapshot_type is not None and snapshot_type not in SNAPSHOT_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported snapshot_type")

    trends = ScoringService(db).score_trends(
        organization.id,
        snapshot_type=snapshot_type,
        days=days,
    )
    return ScoreTrendsResponse(
        days=days,
        series=[
            {
                "snapshot_type": key,
                "points": [
                    {
                        "calculated_at": row.calculated_at,
                        "score": row.score,
                        "grade": row.grade,
                    }
                    for row in rows
                ],
            }
            for key, rows in trends.items()
        ],
    )


@router.get("/snapshots/delta", response_model=ScoreDeltaResponse)
def score_snapshot_delta(
    snapshot_type: str = Query(...),
    days: int = Query(default=30, ge=1, le=3650),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("dashboard:read")),
) -> ScoreDeltaResponse:
    if snapshot_type not in SNAPSHOT_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported snapshot_type")

    delta = ScoringService(db).score_delta(
        organization.id,
        snapshot_type=snapshot_type,
        days=days,
    )
    if delta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not enough snapshots in requested window")
    return ScoreDeltaResponse(**delta)


@router.get("/methodology", response_model=ScoreMethodologyResponse)
def scoring_methodology(
    _: User = Depends(get_current_active_user),
) -> ScoreMethodologyResponse:
    return ScoreMethodologyResponse(**ScoringService.methodology())
