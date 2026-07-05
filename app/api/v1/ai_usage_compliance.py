import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.ai_usage_policy import (
    AiUsagePolicyCheckResponse,
    AiUsagePolicyGapsResponse,
    AiUsagePolicyRunResponse,
    AiUsagePolicySummaryResponse,
)
from app.services.ai_usage_policy_service import AiUsagePolicyService

router = APIRouter(prefix="/ai-usage-compliance", tags=["ai-usage-compliance"])


@router.post("/run", response_model=AiUsagePolicyRunResponse)
def run_ai_usage_compliance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_usage_policy:write")),
) -> AiUsagePolicyRunResponse:
    results = AiUsagePolicyService(db).bulk_run_for_org(organization.id, current_user.id)
    db.commit()
    for row in results:
        db.refresh(row)
    return AiUsagePolicyRunResponse(
        checked_count=len(results),
        results=[AiUsagePolicyCheckResponse.model_validate(row) for row in results],
    )


@router.get("/summary", response_model=AiUsagePolicySummaryResponse)
def get_ai_usage_compliance_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_usage_policy:read")),
) -> AiUsagePolicySummaryResponse:
    summary = AiUsagePolicyService(db).get_summary(organization.id)
    return AiUsagePolicySummaryResponse(**summary)


@router.get("/gaps", response_model=AiUsagePolicyGapsResponse)
def get_ai_usage_compliance_gaps(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_usage_policy:read")),
) -> AiUsagePolicyGapsResponse:
    gaps = AiUsagePolicyService(db).get_gaps(organization.id)
    return AiUsagePolicyGapsResponse(total_gaps=len(gaps), gaps=gaps)


@router.get("/ai-systems/{ai_system_id}", response_model=AiUsagePolicyCheckResponse)
def get_ai_system_usage_compliance(
    ai_system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_usage_policy:read")),
) -> AiUsagePolicyCheckResponse:
    row = AiUsagePolicyService(db).get_latest_check(organization.id, ai_system_id)
    return AiUsagePolicyCheckResponse.model_validate(row)
