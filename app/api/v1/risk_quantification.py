from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.risk_quantification import RiskQuantificationRun
from app.models.user import User
from app.schemas.risk_quantification import RiskQuantificationRequest, RiskQuantificationRunRead
from app.services.audit_service import AuditService
from app.services.risk_quantification_service import RiskQuantificationService

router = APIRouter(prefix="/risks", tags=["risk-quantification"])


def _request_meta(request: Request) -> dict:
    return {
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }


def _run_read(run: RiskQuantificationRun) -> RiskQuantificationRunRead:
    return RiskQuantificationRunRead.model_validate(run)


@router.post(
    "/{risk_id}/quantify",
    response_model=RiskQuantificationRunRead,
    status_code=status.HTTP_201_CREATED,
)
def quantify_risk(
    risk_id: uuid.UUID,
    payload: RiskQuantificationRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("financial_risk:manage")),
) -> RiskQuantificationRunRead:
    service = RiskQuantificationService(db)
    risk = service.get_risk_or_none(organization.id, risk_id)
    if risk is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk not found in this organization")

    try:
        run = service.compute_quantification(
            risk=risk,
            methodology=payload.methodology,
            input_parameters=payload.input_parameters,
            n_iterations=payload.n_iterations,
            computed_by_user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    result = _run_read(run)
    AuditService(db).write_audit_log(
        action="risk_quantification_run.computed",
        entity_type="risk_quantification_run",
        organization_id=organization.id,
        actor_user_id=current_user.id,
        entity_id=run.id,
        after_json=result.model_dump(mode="json"),
        **_request_meta(request),
    )
    db.commit()
    db.refresh(run)
    return _run_read(run)


@router.get(
    "/{risk_id}/quantification-history",
    response_model=list[RiskQuantificationRunRead],
)
def get_quantification_history(
    risk_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("financial_risk:read")),
) -> list[RiskQuantificationRunRead]:
    service = RiskQuantificationService(db)
    risk = service.get_risk_or_none(organization.id, risk_id)
    if risk is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk not found in this organization")

    return [_run_read(run) for run in service.list_runs(organization.id, risk_id)]
