from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.bribery_risk_assessment import BriberyRiskAssessment
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.satellites.tprm_intelligence.bribery_risk_scoring import BriberyRiskScoringService
from app.services.audit_service import AuditService
from app.services.vendor_service import VendorService

router = APIRouter(prefix="/vendors", tags=["tprm-intelligence"])


class GiftHospitalityEntry(BaseModel):
    date: str
    description: str
    value_usd: float


class BriberyRiskComputeRequest(BaseModel):
    jurisdiction: str = Field(min_length=1, max_length=255)
    jurisdiction_cpi_score: int | None = None
    pep_exposure: str = "none"
    gift_hospitality_log: list[GiftHospitalityEntry] | None = None
    industry_category: str | None = None


def _result_payload(row: BriberyRiskAssessment, context: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "id": str(row.id),
        "organization_id": str(row.organization_id),
        "vendor_id": str(row.vendor_id),
        "jurisdiction": row.jurisdiction,
        "jurisdiction_cpi_score": row.jurisdiction_cpi_score,
        "pep_exposure": row.pep_exposure,
        "gift_hospitality_log": row.gift_hospitality_log_json or [],
        "industry_category": row.industry_category,
        "risk_score": row.risk_score,
        "risk_tier": row.risk_tier,
        "scoring_breakdown": row.scoring_breakdown_json,
        "computed_at": row.computed_at.isoformat() if row.computed_at else None,
        "computed_by_user_id": str(row.computed_by_user_id) if row.computed_by_user_id else None,
        "days_since_computed": None,
        "review_overdue": False,
        "score_delta_from_previous": None,
        "context_flags": [],
    }
    if context is not None:
        payload.update(context)
    return payload


@router.post("/{vendor_id}/bribery-risk/compute", status_code=status.HTTP_201_CREATED)
def compute_vendor_bribery_risk(
    vendor_id: uuid.UUID,
    body: BriberyRiskComputeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("anti_bribery:manage")),
) -> dict[str, Any]:
    vendor = VendorService(db).require_vendor_in_org(organization.id, vendor_id)

    gift_log = [entry.model_dump() for entry in body.gift_hospitality_log] if body.gift_hospitality_log else None

    service = BriberyRiskScoringService(db)
    try:
        row = service.compute_risk_assessment(
            organization,
            vendor,
            jurisdiction=body.jurisdiction,
            jurisdiction_cpi_score=body.jurisdiction_cpi_score,
            pep_exposure=body.pep_exposure,
            gift_hospitality_log=gift_log,
            industry_category=body.industry_category,
            computed_by_user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    context = service.build_assessment_context(row, vendor)
    AuditService(db).write_audit_log(
        action="vendor.bribery_risk_assessment.computed",
        entity_type="bribery_risk_assessment",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "vendor_id": str(vendor.id),
            "jurisdiction": row.jurisdiction,
            "risk_score": row.risk_score,
            "risk_tier": row.risk_tier,
            "context_flags": context["context_flags"],
        },
        metadata_json={"source": "tprm_intelligence_satellite"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    # Act on the inconsistent_with_vendor_overall_risk_tier flag rather than
    # letting it sit inert: escalate the under-tiered vendor and create a
    # linked Risk register entry.
    escalation = service.apply_high_risk_escalation(
        organization,
        vendor,
        row,
        context,
        actor_user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    context = {**context, **escalation}

    db.commit()
    db.refresh(row)
    return _result_payload(row, context)


@router.get("/{vendor_id}/bribery-risk")
def get_vendor_bribery_risk(
    vendor_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("anti_bribery:read")),
) -> dict[str, Any]:
    vendor = VendorService(db).require_vendor_in_org(organization.id, vendor_id)
    service = BriberyRiskScoringService(db)
    row = service.latest_assessment(organization.id, vendor_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No anti-bribery risk assessment found for this vendor yet")
    return _result_payload(row, service.build_assessment_context(row, vendor))


@router.get("/{vendor_id}/bribery-risk/history")
def get_vendor_bribery_risk_history(
    vendor_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("anti_bribery:read")),
) -> list[dict[str, Any]]:
    vendor = VendorService(db).require_vendor_in_org(organization.id, vendor_id)
    service = BriberyRiskScoringService(db)
    rows = service.list_assessments(organization.id, vendor_id)
    return [_result_payload(row, service.build_assessment_context(row, vendor)) for row in rows]
