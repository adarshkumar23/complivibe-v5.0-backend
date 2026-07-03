from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.compliance.schemas.compliance_risk_recommendations import (
    ComplianceRiskRecommendationAcceptResponse,
    ComplianceRiskRecommendationActionResponse,
    ComplianceRiskRecommendationGenerateRequest,
    ComplianceRiskRecommendationGenerateResponse,
    ComplianceRiskRecommendationListResponse,
    ComplianceRiskRecommendationRead,
    ComplianceRiskRecommendationSnoozeRequest,
)
from app.compliance.services.compliance_risk_recommendation_service import ComplianceRiskRecommendationService
from app.core.billing_deps import require_feature
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(tags=["compliance-risk-recommendations"])


def _read(row) -> ComplianceRiskRecommendationRead:
    return ComplianceRiskRecommendationRead(
        id=row.id,
        organization_id=row.organization_id,
        business_unit_id=row.business_unit_id,
        recommendation_type=row.recommendation_type,
        title=row.title,
        rationale=row.rationale,
        suggested_category=row.suggested_category,
        suggested_likelihood=row.suggested_likelihood,
        suggested_impact=row.suggested_impact,
        suggested_treatment=row.suggested_treatment,
        linked_risk_id=row.linked_risk_id,
        context_snapshot_json=row.context_snapshot_json,
        provider_used=row.provider_used,
        used_byo_credentials=row.used_byo_credentials,
        status=row.status,
        accepted_risk_id=row.accepted_risk_id,
        generated_by=row.generated_by,
        accepted_by=row.accepted_by,
        dismissed_by=row.dismissed_by,
        snoozed_until=row.snoozed_until,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/compliance/risk-recommendations/generate", response_model=ComplianceRiskRecommendationGenerateResponse)
def generate_recommendations(
    payload: ComplianceRiskRecommendationGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:write")),
    __: Organization = require_feature("ai_risk_recommendations"),
) -> ComplianceRiskRecommendationGenerateResponse:
    rows = ComplianceRiskRecommendationService(db).generate_recommendations(
        org_id=organization.id,
        generated_by=current_user.id,
        business_unit_id=payload.business_unit_id,
    )
    db.commit()
    for row in rows:
        db.refresh(row)
    return ComplianceRiskRecommendationGenerateResponse(items=[_read(row) for row in rows])


@router.get("/compliance/risk-recommendations", response_model=ComplianceRiskRecommendationListResponse)
def list_recommendations(
    status_filter: str | None = Query(default=None, alias="status"),
    recommendation_type: str | None = Query(default=None),
    business_unit_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:read")),
    __: Organization = require_feature("ai_risk_recommendations"),
) -> ComplianceRiskRecommendationListResponse:
    rows, total = ComplianceRiskRecommendationService(db).list_recommendations(
        org_id=organization.id,
        status_filter=status_filter,
        recommendation_type=recommendation_type,
        business_unit_id=business_unit_id,
        page=page,
        page_size=page_size,
    )
    return ComplianceRiskRecommendationListResponse(
        items=[_read(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/compliance/risk-recommendations/{recommendation_id}", response_model=ComplianceRiskRecommendationRead)
def get_recommendation(
    recommendation_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:read")),
    __: Organization = require_feature("ai_risk_recommendations"),
) -> ComplianceRiskRecommendationRead:
    row = ComplianceRiskRecommendationService(db).get_recommendation(
        org_id=organization.id,
        recommendation_id=recommendation_id,
    )
    return _read(row)


@router.post(
    "/compliance/risk-recommendations/{recommendation_id}/accept",
    response_model=ComplianceRiskRecommendationAcceptResponse,
)
def accept_recommendation(
    recommendation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:write")),
    __: Organization = require_feature("ai_risk_recommendations"),
) -> ComplianceRiskRecommendationAcceptResponse:
    row, risk_id = ComplianceRiskRecommendationService(db).accept_recommendation(
        org_id=organization.id,
        recommendation_id=recommendation_id,
        accepted_by=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return ComplianceRiskRecommendationAcceptResponse(
        recommendation=_read(row),
        created_or_updated_risk_id=risk_id,
    )


@router.post(
    "/compliance/risk-recommendations/{recommendation_id}/dismiss",
    response_model=ComplianceRiskRecommendationActionResponse,
)
def dismiss_recommendation(
    recommendation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:write")),
    __: Organization = require_feature("ai_risk_recommendations"),
) -> ComplianceRiskRecommendationActionResponse:
    row = ComplianceRiskRecommendationService(db).dismiss_recommendation(
        org_id=organization.id,
        recommendation_id=recommendation_id,
        dismissed_by=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return ComplianceRiskRecommendationActionResponse(
        id=row.id,
        status=row.status,
        accepted_risk_id=row.accepted_risk_id,
    )


@router.post(
    "/compliance/risk-recommendations/{recommendation_id}/snooze",
    response_model=ComplianceRiskRecommendationActionResponse,
)
def snooze_recommendation(
    recommendation_id: uuid.UUID,
    payload: ComplianceRiskRecommendationSnoozeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:write")),
    __: Organization = require_feature("ai_risk_recommendations"),
) -> ComplianceRiskRecommendationActionResponse:
    row = ComplianceRiskRecommendationService(db).snooze_recommendation(
        org_id=organization.id,
        recommendation_id=recommendation_id,
        snoozed_until=payload.snoozed_until,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return ComplianceRiskRecommendationActionResponse(
        id=row.id,
        status=row.status,
        accepted_risk_id=row.accepted_risk_id,
    )
