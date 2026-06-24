import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.compliance.services.policy_risk_mapping_service import PolicyRiskMappingService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.compliance_policy import CompliancePolicy
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.policy_risk_mapping import PolicyRiskMapping
from app.models.risk import Risk
from app.models.user import User
from app.schemas.policy_risk_mapping import (
    OrgMappingSummaryResponse,
    PolicyRiskCoverageResponse,
    PolicyRiskMappingCreate,
    PolicyRiskMappingResponse,
    PolicyRiskMappingUpdate,
    PolicyRiskPolicyRef,
    PolicyRiskRiskRef,
    RiskPolicyCoverageResponse,
)

router = APIRouter(prefix="/compliance", tags=["policy-risk-mappings"])


def _mapping_read(
    row: PolicyRiskMapping,
    *,
    policy: CompliancePolicy | None = None,
    risk: Risk | None = None,
) -> PolicyRiskMappingResponse:
    return PolicyRiskMappingResponse(
        id=row.id,
        organization_id=row.organization_id,
        policy_id=row.policy_id,
        risk_id=row.risk_id,
        mitigation_strength=row.mitigation_strength,
        notes=row.notes,
        mapped_by=row.mapped_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        policy=PolicyRiskPolicyRef(id=policy.id, name=policy.title) if policy else None,
        risk=PolicyRiskRiskRef(id=risk.id, title=risk.title, severity=risk.severity, status=risk.status) if risk else None,
    )


@router.post("/policy-risk-mappings", response_model=PolicyRiskMappingResponse, status_code=status.HTTP_201_CREATED)
def create_policy_risk_mapping(
    payload: PolicyRiskMappingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("policy_risks:manage")),
) -> PolicyRiskMappingResponse:
    service = PolicyRiskMappingService(db)
    row = service.create_mapping(
        organization.id,
        payload.policy_id,
        payload.risk_id,
        payload.mitigation_strength,
        payload.notes,
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    policy = service.require_policy_in_org(organization.id, row.policy_id)
    risk = service.require_risk_in_org(organization.id, row.risk_id)
    return _mapping_read(row, policy=policy, risk=risk)


@router.get("/policy-risk-mappings/summary", response_model=OrgMappingSummaryResponse)
def get_org_policy_risk_mapping_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("policy_risks:view")),
) -> OrgMappingSummaryResponse:
    payload = PolicyRiskMappingService(db).get_org_mapping_summary(organization.id)
    return OrgMappingSummaryResponse(**payload)


@router.get("/policy-risk-mappings", response_model=list[PolicyRiskMappingResponse])
def list_policy_risk_mappings(
    policy_id: uuid.UUID | None = Query(default=None),
    risk_id: uuid.UUID | None = Query(default=None),
    mitigation_strength: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("policy_risks:view")),
) -> list[PolicyRiskMappingResponse]:
    rows = PolicyRiskMappingService(db).list_mappings(
        organization.id,
        policy_id=policy_id,
        risk_id=risk_id,
        mitigation_strength=mitigation_strength,
    )
    return [_mapping_read(mapping, policy=policy, risk=risk) for mapping, policy, risk in rows]


@router.get("/policy-risk-mappings/{mapping_id}", response_model=PolicyRiskMappingResponse)
def get_policy_risk_mapping(
    mapping_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("policy_risks:view")),
) -> PolicyRiskMappingResponse:
    mapping, policy, risk = PolicyRiskMappingService(db).get_mapping(organization.id, mapping_id)
    return _mapping_read(mapping, policy=policy, risk=risk)


@router.patch("/policy-risk-mappings/{mapping_id}", response_model=PolicyRiskMappingResponse)
def update_policy_risk_mapping(
    mapping_id: uuid.UUID,
    payload: PolicyRiskMappingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("policy_risks:manage")),
) -> PolicyRiskMappingResponse:
    service = PolicyRiskMappingService(db)
    mapping = service.update_mapping(organization.id, mapping_id, payload, current_user.id)
    db.commit()
    db.refresh(mapping)
    policy = service.require_policy_in_org(organization.id, mapping.policy_id)
    risk = service.require_risk_in_org(organization.id, mapping.risk_id)
    return _mapping_read(mapping, policy=policy, risk=risk)


@router.delete("/policy-risk-mappings/{mapping_id}", response_model=PolicyRiskMappingResponse)
def delete_policy_risk_mapping(
    mapping_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("policy_risks:manage")),
) -> PolicyRiskMappingResponse:
    service = PolicyRiskMappingService(db)
    row = service.delete_mapping(organization.id, mapping_id, current_user.id)
    db.commit()
    policy = service.require_policy_in_org(organization.id, row.policy_id)
    risk = service.require_risk_in_org(organization.id, row.risk_id)
    return _mapping_read(row, policy=policy, risk=risk)


@router.get("/policies/{policy_id}/risk-mappings", response_model=list[PolicyRiskMappingResponse])
def list_policy_risk_mappings_for_policy(
    policy_id: uuid.UUID,
    mitigation_strength: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("policy_risks:view")),
) -> list[PolicyRiskMappingResponse]:
    service = PolicyRiskMappingService(db)
    policy = service.require_policy_in_org(organization.id, policy_id)
    rows = service.list_mappings_for_policy(organization.id, policy_id, mitigation_strength=mitigation_strength)
    return [_mapping_read(mapping, policy=policy, risk=risk) for mapping, risk in rows]


@router.get("/policies/{policy_id}/risk-coverage", response_model=PolicyRiskCoverageResponse)
def get_policy_risk_coverage(
    policy_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("policy_risks:view")),
) -> PolicyRiskCoverageResponse:
    payload = PolicyRiskMappingService(db).get_policy_risk_coverage(organization.id, policy_id)
    return PolicyRiskCoverageResponse(**payload)


@router.get("/risks/{risk_id}/policy-mappings", response_model=list[PolicyRiskMappingResponse])
def list_policy_risk_mappings_for_risk(
    risk_id: uuid.UUID,
    mitigation_strength: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("policy_risks:view")),
) -> list[PolicyRiskMappingResponse]:
    service = PolicyRiskMappingService(db)
    risk = service.require_risk_in_org(organization.id, risk_id)
    rows = service.list_mappings_for_risk(organization.id, risk_id, mitigation_strength=mitigation_strength)
    return [_mapping_read(mapping, policy=policy, risk=risk) for mapping, policy in rows]


@router.get("/risks/{risk_id}/policy-coverage", response_model=RiskPolicyCoverageResponse)
def get_risk_policy_coverage(
    risk_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("policy_risks:view")),
) -> RiskPolicyCoverageResponse:
    payload = PolicyRiskMappingService(db).get_risk_policy_coverage(organization.id, risk_id)
    return RiskPolicyCoverageResponse(**payload)
