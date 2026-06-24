import math

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.services.risk_scoring_service import RiskScoringService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.org_risk_settings import OrgRiskSettings
from app.models.organization import Organization
from app.models.user import User
from app.schemas.risk import OrgRiskSettingsRead, OrgRiskSettingsUpdate
from app.services.audit_service import AuditService

router = APIRouter(prefix="/compliance/risk-settings", tags=["risks"])


@router.get("", response_model=OrgRiskSettingsRead)
def get_risk_settings(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risks:read")),
) -> OrgRiskSettingsRead:
    row = db.execute(
        select(OrgRiskSettings).where(OrgRiskSettings.organization_id == organization.id)
    ).scalar_one_or_none()
    if row is None:
        return OrgRiskSettingsRead(
            financial_weight=float(RiskScoringService.DEFAULT_FINANCIAL_WEIGHT),
            brand_weight=float(RiskScoringService.DEFAULT_BRAND_WEIGHT),
            operational_weight=float(RiskScoringService.DEFAULT_OPERATIONAL_WEIGHT),
        )

    return OrgRiskSettingsRead(
        financial_weight=float(row.financial_weight),
        brand_weight=float(row.brand_weight),
        operational_weight=float(row.operational_weight),
    )


@router.put("", response_model=OrgRiskSettingsRead)
def upsert_risk_settings(
    payload: OrgRiskSettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risks:write")),
) -> OrgRiskSettingsRead:
    actual_sum = payload.financial_weight + payload.brand_weight + payload.operational_weight
    if not math.isclose(actual_sum, 1.0, abs_tol=0.001):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Weights must sum to 1.0. Current sum: {actual_sum}",
        )

    row = db.execute(
        select(OrgRiskSettings).where(OrgRiskSettings.organization_id == organization.id)
    ).scalar_one_or_none()

    previous_weights = {
        "financial": float(row.financial_weight) if row is not None else float(RiskScoringService.DEFAULT_FINANCIAL_WEIGHT),
        "brand": float(row.brand_weight) if row is not None else float(RiskScoringService.DEFAULT_BRAND_WEIGHT),
        "operational": float(row.operational_weight) if row is not None else float(RiskScoringService.DEFAULT_OPERATIONAL_WEIGHT),
    }

    if row is None:
        row = OrgRiskSettings(
            organization_id=organization.id,
            financial_weight=payload.financial_weight,
            brand_weight=payload.brand_weight,
            operational_weight=payload.operational_weight,
            updated_by_user_id=current_user.id,
        )
        db.add(row)
    else:
        row.financial_weight = payload.financial_weight
        row.brand_weight = payload.brand_weight
        row.operational_weight = payload.operational_weight
        row.updated_by_user_id = current_user.id

    db.flush()

    new_weights = {
        "financial": float(row.financial_weight),
        "brand": float(row.brand_weight),
        "operational": float(row.operational_weight),
    }

    AuditService(db).write_audit_log(
        action="org_risk_settings.updated",
        entity_type="org_risk_settings",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json={"weights": previous_weights},
        after_json={"weights": new_weights},
        metadata_json={
            "source": "api",
            "context_json": {
                "previous_weights": previous_weights,
                "new_weights": new_weights,
                "updated_by_user_id": str(current_user.id),
            },
        },
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return OrgRiskSettingsRead(
        financial_weight=float(row.financial_weight),
        brand_weight=float(row.brand_weight),
        operational_weight=float(row.operational_weight),
    )
