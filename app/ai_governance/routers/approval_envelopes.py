import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.ai_governance.schemas.guardrails_envelopes import (
    ApprovalEnvelopeRead,
    EnvelopeDecisionRequest,
    EnvelopeRejectRequest,
)
from app.ai_governance.services.approval_envelope_service import ApprovalEnvelopeService
from app.core.deps import get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization

router = APIRouter(prefix="/ai-governance/approval-envelopes", tags=["ai-governance-approval-envelopes"])


@router.get("", response_model=list[ApprovalEnvelopeRead])
def list_envelopes(
    system_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> list[ApprovalEnvelopeRead]:
    service = ApprovalEnvelopeService(db)
    rows = service.list_envelopes(
        organization.id,
        system_id=system_id,
        status_filter=status_filter,
    )
    db.commit()
    return [ApprovalEnvelopeRead.model_validate(item) for item in service.envelope_payloads(organization.id, rows)]


@router.get("/{envelope_id}", response_model=ApprovalEnvelopeRead)
def get_envelope(
    envelope_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> ApprovalEnvelopeRead:
    service = ApprovalEnvelopeService(db)
    row = service.get_envelope(organization.id, envelope_id)
    db.commit()
    db.refresh(row)
    return ApprovalEnvelopeRead.model_validate(service.envelope_payloads(organization.id, [row])[0])


@router.post("/{envelope_id}/approve", response_model=ApprovalEnvelopeRead)
def approve_envelope(
    envelope_id: uuid.UUID,
    payload: EnvelopeDecisionRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    current_membership: Membership = Depends(require_permission("ai_governance:approve")),
) -> ApprovalEnvelopeRead:
    service = ApprovalEnvelopeService(db)
    row = service.approve_envelope(
        organization.id,
        envelope_id,
        current_membership.user_id,
        payload.notes,
    )
    db.commit()
    db.refresh(row)
    return ApprovalEnvelopeRead.model_validate(service.envelope_payloads(organization.id, [row])[0])


@router.post("/{envelope_id}/reject", response_model=ApprovalEnvelopeRead)
def reject_envelope(
    envelope_id: uuid.UUID,
    payload: EnvelopeRejectRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    current_membership: Membership = Depends(require_permission("ai_governance:approve")),
) -> ApprovalEnvelopeRead:
    service = ApprovalEnvelopeService(db)
    row = service.reject_envelope(
        organization.id,
        envelope_id,
        current_membership.user_id,
        payload.notes,
    )
    db.commit()
    db.refresh(row)
    return ApprovalEnvelopeRead.model_validate(service.envelope_payloads(organization.id, [row])[0])
