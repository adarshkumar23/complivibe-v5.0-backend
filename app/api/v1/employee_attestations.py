import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.compliance.services.employee_attestation_service import AttestationCampaignService, AttestationRecordService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.organization import Organization
from app.models.policy_attestation_campaign import PolicyAttestationCampaign
from app.models.policy_attestation_record import PolicyAttestationRecord
from app.models.user import User
from app.schemas.attestation import (
    AttestationCampaignCreate,
    AttestationCampaignCreateResponse,
    AttestationCampaignRef,
    AttestationCampaignResponse,
    AttestationCampaignUpdate,
    AttestationDashboardResponse,
    AttestationExemptionRequest,
    AttestationRecordResponse,
    AttestationReminderResponse,
    AttestationUserBreakdownResponse,
    PolicyAttestationSummaryResponse,
)

router = APIRouter(prefix="/compliance", tags=["employee-attestations"])


def _campaign_read(service: AttestationCampaignService, row: PolicyAttestationCampaign) -> AttestationCampaignResponse:
    return AttestationCampaignResponse(**service.campaign_with_stats(row))


def _record_read(
    row: PolicyAttestationRecord,
    campaign: PolicyAttestationCampaign,
    *,
    policy_name: str | None = None,
) -> AttestationRecordResponse:
    return AttestationRecordResponse(
        id=row.id,
        organization_id=row.organization_id,
        campaign_id=row.campaign_id,
        user_id=row.user_id,
        status=row.status,
        attested_at=row.attested_at,
        expires_at=row.expires_at,
        exemption_reason=row.exemption_reason,
        reminder_sent_at=row.reminder_sent_at,
        created_at=row.created_at,
        campaign=AttestationCampaignRef(
            id=campaign.id,
            name=campaign.name,
            policy_id=campaign.policy_id,
            policy_name=policy_name,
            policy_version=campaign.policy_version,
            due_date=campaign.due_date,
            status=campaign.status,
        ),
    )


@router.get("/attestation-campaigns/dashboard", response_model=AttestationDashboardResponse)
def attestation_dashboard(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("attestations:view")),
) -> AttestationDashboardResponse:
    service = AttestationCampaignService(db)
    payload = service.get_dashboard(organization.id)
    return AttestationDashboardResponse(**payload)


@router.patch("/attestation-campaigns/{campaign_id}", response_model=AttestationCampaignResponse)
def update_attestation_campaign(
    campaign_id: uuid.UUID,
    payload: AttestationCampaignUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("attestations:manage")),
) -> AttestationCampaignResponse:
    service = AttestationCampaignService(db)
    row = service.update_campaign(organization.id, campaign_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _campaign_read(service, row)


@router.delete("/attestation-campaigns/{campaign_id}", response_model=AttestationCampaignResponse)
def cancel_attestation_campaign(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("attestations:manage")),
) -> AttestationCampaignResponse:
    service = AttestationCampaignService(db)
    row = service.cancel_campaign(organization.id, campaign_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _campaign_read(service, row)


@router.get("/attestation-campaigns/{campaign_id}/completion", response_model=list[AttestationUserBreakdownResponse])
def attestation_campaign_completion(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("attestations:view")),
) -> list[AttestationUserBreakdownResponse]:
    rows = AttestationCampaignService(db).get_campaign_completion(organization.id, campaign_id)
    return [AttestationUserBreakdownResponse(**row) for row in rows]


@router.post("/attestation-campaigns/{campaign_id}/reminders", response_model=AttestationReminderResponse)
def send_attestation_bulk_reminders(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("attestations:manage")),
) -> AttestationReminderResponse:
    count = AttestationRecordService(db).send_bulk_reminders(organization.id, campaign_id, current_user.id)
    db.commit()
    return AttestationReminderResponse(reminders_queued=count)


@router.post("/attestation-campaigns/{campaign_id}/exempt/{user_id}", response_model=AttestationRecordResponse)
def exempt_user_attestation(
    campaign_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: AttestationExemptionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("attestations:manage")),
) -> AttestationRecordResponse:
    service = AttestationRecordService(db)
    row = service.exempt_user(organization.id, campaign_id, user_id, payload.reason, current_user.id)
    campaign = service.campaign_service.require_campaign(organization.id, campaign_id)
    policy_name = service.campaign_service.require_policy_in_org(organization.id, campaign.policy_id).title
    db.commit()
    db.refresh(row)
    return _record_read(row, campaign, policy_name=policy_name)


@router.post("/attestation-campaigns/{campaign_id}/remind/{user_id}", response_model=AttestationRecordResponse)
def send_single_attestation_reminder(
    campaign_id: uuid.UUID,
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("attestations:manage")),
) -> AttestationRecordResponse:
    service = AttestationRecordService(db)
    row = service.send_reminder(organization.id, campaign_id, user_id, current_user.id)
    campaign = service.campaign_service.require_campaign(organization.id, campaign_id)
    policy_name = service.campaign_service.require_policy_in_org(organization.id, campaign.policy_id).title
    db.commit()
    db.refresh(row)
    return _record_read(row, campaign, policy_name=policy_name)


@router.get("/attestation-records/me", response_model=list[AttestationRecordResponse])
def list_my_attestation_records(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("attestations:view")),
) -> list[AttestationRecordResponse]:
    rows = AttestationRecordService(db).get_user_attestations(organization.id, current_user.id)
    return [_record_read(record, campaign, policy_name=policy.title) for record, campaign, policy in rows]


@router.get("/attestation-records/user/{user_id}", response_model=list[AttestationRecordResponse])
def list_user_attestation_records(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("attestations:manage")),
) -> list[AttestationRecordResponse]:
    rows = AttestationRecordService(db).get_user_attestations(organization.id, user_id)
    return [_record_read(record, campaign, policy_name=policy.title) for record, campaign, policy in rows]


@router.get("/policies/{policy_id}/attestation-summary", response_model=PolicyAttestationSummaryResponse)
def policy_attestation_summary(
    policy_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("attestations:view")),
) -> PolicyAttestationSummaryResponse:
    payload = AttestationCampaignService(db).get_policy_completion_rate(organization.id, policy_id)
    return PolicyAttestationSummaryResponse(**payload)
