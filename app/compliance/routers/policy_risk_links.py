import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.compliance.schemas.policy_risk_link import PolicyRef, PolicyRiskLinkCreateRequest, PolicyRiskLinkResponse, RiskRef
from app.compliance.services.policy_risk_link_service import PolicyRiskLinkService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/compliance", tags=["policy-risk-links"])


@router.post("/policies/{policy_id}/risks", response_model=PolicyRiskLinkResponse, status_code=status.HTTP_201_CREATED)
def link_policy_risk(
    policy_id: uuid.UUID,
    payload: PolicyRiskLinkCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:write")),
) -> PolicyRiskLinkResponse:
    row = PolicyRiskLinkService(db).link_risk(
        org_id=organization.id,
        policy_id=policy_id,
        risk_id=payload.risk_id,
        created_by=current_user.id,
        link_reason=payload.link_reason,
    )
    db.commit()
    db.refresh(row)
    return PolicyRiskLinkResponse(policy_id=row.policy_id, risk_id=row.risk_id, status=row.status)


@router.delete("/policies/{policy_id}/risks/{risk_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_policy_risk(
    policy_id: uuid.UUID,
    risk_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:write")),
) -> None:
    PolicyRiskLinkService(db).unlink_risk(
        org_id=organization.id,
        policy_id=policy_id,
        risk_id=risk_id,
        actor_user_id=current_user.id,
    )
    db.commit()
    return None


@router.get("/policies/{policy_id}/risks", response_model=list[RiskRef])
def list_risks_for_policy(
    policy_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:read")),
) -> list[RiskRef]:
    rows = PolicyRiskLinkService(db).list_risks_for_policy(org_id=organization.id, policy_id=policy_id)
    return [RiskRef(id=row.id, title=row.title, status=row.status) for row in rows]


@router.get("/risks/{risk_id}/policies", response_model=list[PolicyRef])
def list_policies_for_risk(
    risk_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:read")),
) -> list[PolicyRef]:
    rows = PolicyRiskLinkService(db).list_policies_for_risk(org_id=organization.id, risk_id=risk_id)
    return [PolicyRef(id=row.id, title=row.title, status=row.status) for row in rows]
