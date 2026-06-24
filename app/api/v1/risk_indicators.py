import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.compliance.services.kri_calculator import KRICalculator
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.risk import Risk
from app.models.risk_indicator import RiskIndicator
from app.models.user import User
from app.schemas.risk_indicator import (
    RiskIndicatorArchiveRequest,
    RiskIndicatorCreate,
    RiskIndicatorDetail,
    RiskIndicatorLinkedRiskSummary,
    RiskIndicatorRead,
    RiskIndicatorSummary,
    RiskIndicatorUpdate,
)
from app.services.audit_service import AuditService

router = APIRouter(prefix="/compliance/risk-indicators", tags=["risk-indicators"])


def _as_float(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _indicator_read(row: RiskIndicator) -> RiskIndicatorRead:
    return RiskIndicatorRead(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        description=row.description,
        metric_type=row.metric_type,
        target_value=_as_float(row.target_value) or 0.0,
        warning_threshold=_as_float(row.warning_threshold) or 0.0,
        critical_threshold=_as_float(row.critical_threshold) or 0.0,
        current_value=_as_float(row.current_value),
        status=row.status,
        owner_user_id=row.owner_user_id,
        linked_risk_id=row.linked_risk_id,
        last_calculated_at=row.last_calculated_at,
        notes=row.notes,
        tags_json=row.tags_json,
        is_active=row.is_active,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        archive_reason=row.archive_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _require_active_member(organization_id: uuid.UUID, user_id: uuid.UUID, db: Session) -> None:
    membership = db.execute(
        select(Membership).where(
            Membership.organization_id == organization_id,
            Membership.user_id == user_id,
            Membership.status == "active",
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="owner_user_id must be an active member of the organization")

    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None or not user.is_active or user.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="owner_user_id must be an active member of the organization")


def _require_risk_in_org(organization_id: uuid.UUID, risk_id: uuid.UUID, db: Session) -> Risk:
    risk = db.execute(
        select(Risk).where(
            Risk.organization_id == organization_id,
            Risk.id == risk_id,
        )
    ).scalar_one_or_none()
    if risk is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="linked_risk_id must belong to the same organization")
    return risk


def _threshold_validation(warning_threshold: float, critical_threshold: float) -> None:
    if warning_threshold >= critical_threshold:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="warning_threshold must be less than critical_threshold")


@router.post("", response_model=RiskIndicatorRead, status_code=status.HTTP_201_CREATED)
def create_risk_indicator(
    payload: RiskIndicatorCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risk_indicators:write")),
) -> RiskIndicatorRead:
    _threshold_validation(payload.warning_threshold, payload.critical_threshold)
    _require_active_member(organization.id, payload.owner_user_id, db)
    if payload.linked_risk_id is not None:
        _require_risk_in_org(organization.id, payload.linked_risk_id, db)

    row = RiskIndicator(
        organization_id=organization.id,
        name=payload.name,
        description=payload.description,
        metric_type=payload.metric_type,
        target_value=payload.target_value,
        warning_threshold=payload.warning_threshold,
        critical_threshold=payload.critical_threshold,
        status="not_calculated",
        owner_user_id=payload.owner_user_id,
        linked_risk_id=payload.linked_risk_id,
        notes=payload.notes,
        tags_json=payload.tags_json,
        is_active=True,
    )
    db.add(row)
    db.flush()

    AuditService(db).write_audit_log(
        action="risk_indicator.created",
        entity_type="risk_indicator",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "name": row.name,
            "metric_type": row.metric_type,
            "status": row.status,
            "owner_user_id": str(row.owner_user_id),
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _indicator_read(row)


@router.get("", response_model=list[RiskIndicatorRead])
def list_risk_indicators(
    status_filter: str | None = Query(default=None, alias="status"),
    metric_type: str | None = Query(default=None),
    is_active: bool = Query(default=True),
    include_archived: bool = Query(default=False),
    owner_user_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risk_indicators:read")),
) -> list[RiskIndicatorRead]:
    stmt = select(RiskIndicator).where(RiskIndicator.organization_id == organization.id)
    if status_filter is not None:
        stmt = stmt.where(RiskIndicator.status == status_filter)
    if metric_type is not None:
        stmt = stmt.where(RiskIndicator.metric_type == metric_type)
    if owner_user_id is not None:
        stmt = stmt.where(RiskIndicator.owner_user_id == owner_user_id)

    stmt = stmt.where(RiskIndicator.is_active == is_active)
    if not include_archived:
        stmt = stmt.where(RiskIndicator.archived_at.is_(None))

    rows = db.execute(stmt.order_by(RiskIndicator.created_at.desc()).limit(limit).offset(offset)).scalars().all()
    return [_indicator_read(row) for row in rows]


@router.get("/summary", response_model=RiskIndicatorSummary)
def risk_indicator_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risk_indicators:read")),
) -> RiskIndicatorSummary:
    base = select(RiskIndicator).where(
        RiskIndicator.organization_id == organization.id,
        RiskIndicator.is_active.is_(True),
        RiskIndicator.archived_at.is_(None),
    )

    rows = db.execute(base).scalars().all()
    total_indicators = len(rows)
    by_status: dict[str, int] = {}
    by_metric_type: dict[str, int] = {}
    oldest_last_calculated = None
    for row in rows:
        by_status[row.status] = by_status.get(row.status, 0) + 1
        by_metric_type[row.metric_type] = by_metric_type.get(row.metric_type, 0) + 1
        if row.last_calculated_at is not None:
            if oldest_last_calculated is None or row.last_calculated_at < oldest_last_calculated:
                oldest_last_calculated = row.last_calculated_at

    return RiskIndicatorSummary(
        total_indicators=total_indicators,
        by_status=by_status,
        by_metric_type=by_metric_type,
        last_calculated_at=oldest_last_calculated,
        critical_count=by_status.get("red", 0),
        warning_count=by_status.get("amber", 0),
    )


@router.get("/{indicator_id}", response_model=RiskIndicatorDetail)
def get_risk_indicator(
    indicator_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risk_indicators:read")),
) -> RiskIndicatorDetail:
    row = KRICalculator.require_indicator_in_org(organization.id, indicator_id, db)
    payload = _indicator_read(row).model_dump()

    linked_risk_summary = None
    if row.linked_risk_id is not None:
        linked = db.execute(
            select(Risk).where(
                Risk.organization_id == organization.id,
                Risk.id == row.linked_risk_id,
            )
        ).scalar_one_or_none()
        if linked is not None:
            linked_risk_summary = RiskIndicatorLinkedRiskSummary(
                id=linked.id,
                title=linked.title,
                status=linked.status,
                severity=linked.severity,
            )

    return RiskIndicatorDetail(**payload, linked_risk_summary=linked_risk_summary)


@router.patch("/{indicator_id}", response_model=RiskIndicatorRead)
def update_risk_indicator(
    indicator_id: uuid.UUID,
    payload: RiskIndicatorUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risk_indicators:write")),
) -> RiskIndicatorRead:
    row = KRICalculator.require_indicator_in_org(organization.id, indicator_id, db)
    if row.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived indicators cannot be updated")

    changes = payload.model_dump(exclude_unset=True)
    warning_threshold = float(changes.get("warning_threshold", row.warning_threshold))
    critical_threshold = float(changes.get("critical_threshold", row.critical_threshold))
    _threshold_validation(warning_threshold, critical_threshold)

    if "owner_user_id" in changes and changes["owner_user_id"] is not None:
        _require_active_member(organization.id, changes["owner_user_id"], db)
    if "linked_risk_id" in changes and changes["linked_risk_id"] is not None:
        _require_risk_in_org(organization.id, changes["linked_risk_id"], db)

    before = {
        "name": row.name,
        "target_value": _as_float(row.target_value),
        "warning_threshold": _as_float(row.warning_threshold),
        "critical_threshold": _as_float(row.critical_threshold),
        "owner_user_id": str(row.owner_user_id),
        "linked_risk_id": str(row.linked_risk_id) if row.linked_risk_id else None,
        "is_active": row.is_active,
    }

    for field, value in changes.items():
        setattr(row, field, value)
    db.flush()

    AuditService(db).write_audit_log(
        action="risk_indicator.updated",
        entity_type="risk_indicator",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "name": row.name,
            "target_value": _as_float(row.target_value),
            "warning_threshold": _as_float(row.warning_threshold),
            "critical_threshold": _as_float(row.critical_threshold),
            "owner_user_id": str(row.owner_user_id),
            "linked_risk_id": str(row.linked_risk_id) if row.linked_risk_id else None,
            "is_active": row.is_active,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _indicator_read(row)


@router.post("/{indicator_id}/recalculate", response_model=RiskIndicatorRead)
def recalculate_risk_indicator(
    indicator_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risk_indicators:write")),
) -> RiskIndicatorRead:
    row = KRICalculator.recalculate_and_persist(
        indicator_id,
        organization.id,
        db,
        actor_user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return _indicator_read(row)


@router.post("/{indicator_id}/archive", response_model=RiskIndicatorRead)
def archive_risk_indicator(
    indicator_id: uuid.UUID,
    payload: RiskIndicatorArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risk_indicators:write")),
) -> RiskIndicatorRead:
    row = KRICalculator.require_indicator_in_org(organization.id, indicator_id, db)
    if row.archived_at is not None:
        return _indicator_read(row)

    before = {
        "archived_at": row.archived_at.isoformat() if row.archived_at else None,
        "archived_by_user_id": str(row.archived_by_user_id) if row.archived_by_user_id else None,
        "archive_reason": row.archive_reason,
        "is_active": row.is_active,
    }

    row.archived_at = KRICalculator.utcnow()
    row.archived_by_user_id = current_user.id
    row.archive_reason = payload.archive_reason
    row.is_active = False
    db.flush()

    AuditService(db).write_audit_log(
        action="risk_indicator.archived",
        entity_type="risk_indicator",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "archived_at": row.archived_at.isoformat() if row.archived_at else None,
            "archived_by_user_id": str(row.archived_by_user_id) if row.archived_by_user_id else None,
            "archive_reason": row.archive_reason,
            "is_active": row.is_active,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _indicator_read(row)
