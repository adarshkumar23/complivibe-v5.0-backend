import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.compliance.services.risk_appetite_service import RiskAppetiteService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.risk import Risk
from app.models.risk_appetite_threshold import RiskAppetiteThreshold
from app.models.user import User
from app.schemas.risk_appetite import (
    RiskAppetiteBreachRead,
    RiskAppetiteBreachRiskSummary,
    RiskAppetiteSummary,
    RiskAppetiteThresholdCreate,
    RiskAppetiteThresholdDeactivateRequest,
    RiskAppetiteThresholdRead,
    RiskAppetiteThresholdUpdate,
)
from app.services.audit_service import AuditService

router = APIRouter(prefix="/compliance/risk-appetite", tags=["risk-appetite"])
ALL_RISK_CATEGORIES = ["operational", "financial", "compliance", "reputational", "technology", "vendor"]


def _threshold_read(row: RiskAppetiteThreshold) -> RiskAppetiteThresholdRead:
    return RiskAppetiteThresholdRead(
        id=row.id,
        organization_id=row.organization_id,
        scope_type=row.scope_type,
        scope_id=row.scope_id,
        risk_category=row.risk_category,
        max_acceptable_score=row.max_acceptable_score,
        escalation_owner_id=row.escalation_owner_id,
        is_active=row.is_active,
        notes=row.notes,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("", response_model=RiskAppetiteThresholdRead, status_code=status.HTTP_201_CREATED)
def create_threshold(
    payload: RiskAppetiteThresholdCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risk_appetite:write")),
) -> RiskAppetiteThresholdRead:
    service = RiskAppetiteService(db)

    if payload.scope_type == "org" and payload.scope_id is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scope_id must be null when scope_type is org")
    if payload.scope_type == "business_unit" and payload.scope_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scope_id is required when scope_type is business_unit")

    service.ensure_active_member(organization.id, payload.escalation_owner_id, field_name="escalation_owner_id")
    service.ensure_no_active_duplicate(
        organization_id=organization.id,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        risk_category=payload.risk_category,
    )

    row = RiskAppetiteThreshold(
        organization_id=organization.id,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        risk_category=payload.risk_category,
        max_acceptable_score=payload.max_acceptable_score,
        escalation_owner_id=payload.escalation_owner_id,
        is_active=True,
        notes=payload.notes,
        created_by_user_id=current_user.id,
    )
    db.add(row)
    db.flush()

    AuditService(db).write_audit_log(
        action="risk_appetite.created",
        entity_type="risk_appetite_threshold",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "scope_type": row.scope_type,
            "scope_id": str(row.scope_id) if row.scope_id else None,
            "risk_category": row.risk_category,
            "max_acceptable_score": row.max_acceptable_score,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _threshold_read(row)


@router.get("", response_model=list[RiskAppetiteThresholdRead])
def list_thresholds(
    scope_type: str | None = Query(default=None),
    risk_category: str | None = Query(default=None),
    is_active: bool = Query(default=True),
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risk_appetite:read")),
) -> list[RiskAppetiteThresholdRead]:
    stmt = select(RiskAppetiteThreshold).where(RiskAppetiteThreshold.organization_id == organization.id)
    if scope_type is not None:
        stmt = stmt.where(RiskAppetiteThreshold.scope_type == scope_type)
    if risk_category is not None:
        stmt = stmt.where(RiskAppetiteThreshold.risk_category == risk_category)
    if not include_inactive:
        stmt = stmt.where(RiskAppetiteThreshold.is_active.is_(is_active))

    rows = db.execute(stmt.order_by(RiskAppetiteThreshold.created_at.desc())).scalars().all()
    return [_threshold_read(row) for row in rows]


@router.get("/summary", response_model=RiskAppetiteSummary)
def summary_thresholds(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risk_appetite:read")),
) -> RiskAppetiteSummary:
    rows = db.execute(
        select(RiskAppetiteThreshold).where(RiskAppetiteThreshold.organization_id == organization.id)
    ).scalars().all()
    total_thresholds = len(rows)
    active_rows = [row for row in rows if row.is_active]

    by_category: dict[str, int] = {}
    for row in rows:
        by_category[row.risk_category] = by_category.get(row.risk_category, 0) + 1

    breach_count = int(
        db.execute(
            select(func.count(ControlMonitoringAlert.id)).where(
                ControlMonitoringAlert.organization_id == organization.id,
                ControlMonitoringAlert.alert_type == "risk_threshold_breach",
                ControlMonitoringAlert.status == "open",
            )
        ).scalar_one()
    )

    active_org_categories = {
        row.risk_category
        for row in active_rows
        if row.scope_type == "org" and row.scope_id is None
    }
    categories_without_threshold = [c for c in ALL_RISK_CATEGORIES if c not in active_org_categories]

    return RiskAppetiteSummary(
        total_thresholds=total_thresholds,
        active_thresholds=len(active_rows),
        by_category=by_category,
        breach_count=breach_count,
        categories_without_threshold=categories_without_threshold,
    )


@router.get("/breaches", response_model=list[RiskAppetiteBreachRead])
def list_live_breaches(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risk_appetite:read")),
) -> list[RiskAppetiteBreachRead]:
    alerts = db.execute(
        select(ControlMonitoringAlert)
        .where(
            ControlMonitoringAlert.organization_id == organization.id,
            ControlMonitoringAlert.alert_type == "risk_threshold_breach",
            ControlMonitoringAlert.status == "open",
        )
        .order_by(ControlMonitoringAlert.created_at.desc())
    ).scalars().all()

    risk_ids: list[uuid.UUID] = []
    for alert in alerts:
        if isinstance(alert.alert_context_json, dict):
            raw_risk_id = alert.alert_context_json.get("risk_id")
            if isinstance(raw_risk_id, str):
                try:
                    risk_ids.append(uuid.UUID(raw_risk_id))
                except ValueError:
                    continue
    risk_map = {
        row.id: row
        for row in db.execute(
            select(Risk).where(Risk.organization_id == organization.id, Risk.id.in_(risk_ids))
        ).scalars().all()
    } if risk_ids else {}

    payload: list[RiskAppetiteBreachRead] = []
    for alert in alerts:
        ctx = alert.alert_context_json if isinstance(alert.alert_context_json, dict) else {}

        threshold_id = None
        raw_threshold_id = ctx.get("threshold_id")
        if isinstance(raw_threshold_id, str):
            try:
                threshold_id = uuid.UUID(raw_threshold_id)
            except ValueError:
                threshold_id = None

        scope_id = None
        raw_scope_id = ctx.get("scope_id")
        if isinstance(raw_scope_id, str):
            try:
                scope_id = uuid.UUID(raw_scope_id)
            except ValueError:
                scope_id = None

        risk_summary = None
        raw_risk_id = ctx.get("risk_id")
        if isinstance(raw_risk_id, str):
            try:
                risk_id = uuid.UUID(raw_risk_id)
            except ValueError:
                risk_id = None
            if risk_id is not None and risk_id in risk_map:
                risk_row = risk_map[risk_id]
                risk_summary = RiskAppetiteBreachRiskSummary(
                    id=risk_row.id,
                    name=risk_row.title,
                    score=int(risk_row.inherent_score),
                    category=risk_row.category,
                )

        payload.append(
            RiskAppetiteBreachRead(
                alert_id=alert.id,
                status=alert.status,
                severity=alert.severity,
                title=alert.title,
                threshold_id=threshold_id,
                scope_type=ctx.get("scope_type") if isinstance(ctx.get("scope_type"), str) else None,
                scope_id=scope_id,
                risk_category=ctx.get("risk_category") if isinstance(ctx.get("risk_category"), str) else None,
                new_score=int(ctx["new_score"]) if isinstance(ctx.get("new_score"), int) else None,
                max_acceptable_score=(
                    int(ctx["max_acceptable_score"]) if isinstance(ctx.get("max_acceptable_score"), int) else None
                ),
                risk=risk_summary,
                created_at=alert.created_at,
            )
        )

    return payload


@router.get("/{threshold_id}", response_model=RiskAppetiteThresholdRead)
def get_threshold(
    threshold_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risk_appetite:read")),
) -> RiskAppetiteThresholdRead:
    row = RiskAppetiteService(db).require_threshold_in_org(organization.id, threshold_id)
    return _threshold_read(row)


@router.patch("/{threshold_id}", response_model=RiskAppetiteThresholdRead)
def update_threshold(
    threshold_id: uuid.UUID,
    payload: RiskAppetiteThresholdUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risk_appetite:write")),
) -> RiskAppetiteThresholdRead:
    service = RiskAppetiteService(db)
    row = service.require_threshold_in_org(organization.id, threshold_id)

    changes = payload.model_dump(exclude_unset=True)
    if "escalation_owner_id" in changes and changes["escalation_owner_id"] is not None:
        service.ensure_active_member(organization.id, changes["escalation_owner_id"], field_name="escalation_owner_id")

    before = {
        "max_acceptable_score": row.max_acceptable_score,
        "escalation_owner_id": str(row.escalation_owner_id),
        "notes": row.notes,
    }
    for field, value in changes.items():
        setattr(row, field, value)
    db.flush()

    AuditService(db).write_audit_log(
        action="risk_appetite.updated",
        entity_type="risk_appetite_threshold",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "max_acceptable_score": row.max_acceptable_score,
            "escalation_owner_id": str(row.escalation_owner_id),
            "notes": row.notes,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _threshold_read(row)


@router.post("/{threshold_id}/deactivate", response_model=RiskAppetiteThresholdRead)
def deactivate_threshold(
    threshold_id: uuid.UUID,
    payload: RiskAppetiteThresholdDeactivateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risk_appetite:write")),
) -> RiskAppetiteThresholdRead:
    row = RiskAppetiteService(db).require_threshold_in_org(organization.id, threshold_id)

    if row.is_active:
        row.is_active = False
        existing = row.notes or ""
        reason_line = f"Deactivated: {payload.reason}"
        row.notes = f"{existing}\n{reason_line}".strip() if existing else reason_line
        db.flush()

        AuditService(db).write_audit_log(
            action="risk_appetite.deactivated",
            entity_type="risk_appetite_threshold",
            entity_id=row.id,
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={"is_active": row.is_active},
            metadata_json={"source": "api", "reason": payload.reason},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

    db.commit()
    db.refresh(row)
    return _threshold_read(row)
