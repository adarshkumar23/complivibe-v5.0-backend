import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.compliance.schemas.attestations_exceptions import (
    AttestationCampaignCreateRequest,
    AttestationCampaignResponse,
    AttestationDeclineRequest,
    AttestationRecordResponse,
    AttestationSummaryResponse,
)
from app.compliance.services.policy_attestation_service import PolicyAttestationService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/compliance", tags=["policy_attestations"])


def _campaign_read(row) -> AttestationCampaignResponse:
    return AttestationCampaignResponse(
        id=row.id,
        organization_id=row.organization_id,
        policy_id=row.policy_id,
        policy_version_id=row.policy_version_id,
        title=row.title or row.name,
        description=row.description,
        attestation_text_shown=row.attestation_text_shown or "",
        content_hash=row.content_hash or "",
        due_date=row.due_date,
        status=row.status,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _att_read(row) -> AttestationRecordResponse:
    return AttestationRecordResponse(
        id=row.id,
        organization_id=row.organization_id,
        campaign_id=row.campaign_id,
        user_id=row.user_id,
        status=row.status,
        attested_at=row.attested_at,
        declined_at=row.declined_at,
        decline_reason=row.decline_reason,
        ip_address=row.ip_address,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/attestation-campaigns", response_model=AttestationSummaryResponse, status_code=status.HTTP_201_CREATED)
def create_campaign(
    payload: AttestationCampaignCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:write")),
) -> AttestationSummaryResponse:
    service = PolicyAttestationService(db)
    campaign, _ = service.create_campaign(
        organization.id,
        payload.policy_id,
        payload.title,
        payload.description,
        payload.due_date,
        current_user.id,
        attestation_text=payload.attestation_text,
        policy_version_id=payload.policy_version_id,
    )
    summary = service.get_campaign_summary(organization.id, campaign.id)
    db.commit()
    return AttestationSummaryResponse(
        campaign=_campaign_read(summary["campaign"]),
        total_members=summary["total_members"],
        attested_count=summary["attested_count"],
        declined_count=summary["declined_count"],
        pending_count=summary["pending_count"],
        completion_pct=summary["completion_pct"],
        policy_changed_since_campaign_start=summary["policy_changed_since_campaign_start"],
        current_policy_version=summary["current_policy_version"],
    )


@router.get("/attestation-campaigns", response_model=list[AttestationCampaignResponse])
def list_campaigns(
    policy_id: uuid.UUID | None = None,
    status_value: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:read")),
) -> list[AttestationCampaignResponse]:
    rows = PolicyAttestationService(db).list_campaigns(
        organization.id,
        policy_id=policy_id,
        status_value=status_value,
        page=page,
        page_size=page_size,
    )
    return [_campaign_read(r) for r in rows]


@router.get("/attestation-campaigns/{campaign_id}", response_model=AttestationSummaryResponse)
def get_campaign(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:read")),
) -> AttestationSummaryResponse:
    summary = PolicyAttestationService(db).get_campaign_summary(organization.id, campaign_id)
    return AttestationSummaryResponse(
        campaign=_campaign_read(summary["campaign"]),
        total_members=summary["total_members"],
        attested_count=summary["attested_count"],
        declined_count=summary["declined_count"],
        pending_count=summary["pending_count"],
        completion_pct=summary["completion_pct"],
        policy_changed_since_campaign_start=summary["policy_changed_since_campaign_start"],
        current_policy_version=summary["current_policy_version"],
    )


@router.get("/attestation-campaigns/{campaign_id}/attestations", response_model=list[AttestationRecordResponse])
def list_campaign_attestations(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:read")),
) -> list[AttestationRecordResponse]:
    rows = PolicyAttestationService(db).list_campaign_attestations(organization.id, campaign_id)
    return [_att_read(r) for r in rows]


@router.post("/attestation-campaigns/{campaign_id}/attest", response_model=AttestationRecordResponse)
def attest_campaign(
    campaign_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> AttestationRecordResponse:
    row = PolicyAttestationService(db).attest(
        organization.id,
        campaign_id,
        current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return _att_read(row)


@router.post("/attestation-campaigns/{campaign_id}/decline", response_model=AttestationRecordResponse)
def decline_campaign(
    campaign_id: uuid.UUID,
    payload: AttestationDeclineRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> AttestationRecordResponse:
    row = PolicyAttestationService(db).decline(
        organization.id,
        campaign_id,
        current_user.id,
        decline_reason=payload.decline_reason,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return _att_read(row)


@router.get("/my-attestations", response_model=list[AttestationRecordResponse])
def my_attestations(
    status_value: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> list[AttestationRecordResponse]:
    rows = PolicyAttestationService(db).list_user_attestations(organization.id, current_user.id, status_value=status_value)
    return [_att_read(r) for r in rows]
