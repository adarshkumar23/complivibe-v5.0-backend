import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.compliance.services.vendor_mitigation_service import VendorMitigationService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.models.vendor_mitigation_action import VendorMitigationAction
from app.models.vendor_mitigation_case import VendorMitigationCase
from app.schemas.vendor_mitigation import (
    VendorMitigationActionCreate,
    VendorMitigationActionEvidenceSubmitRequest,
    VendorMitigationActionRead,
    VendorMitigationActionRejectRequest,
    VendorMitigationCaseCreate,
    VendorMitigationCaseEscalateRequest,
    VendorMitigationCaseRead,
    VendorMitigationCaseTransitionRequest,
    VendorMitigationSummary,
)

router = APIRouter(prefix="/compliance/vendor-mitigation", tags=["vendor-mitigation"])


def _case_read(row: VendorMitigationCase) -> VendorMitigationCaseRead:
    return VendorMitigationCaseRead(
        id=row.id,
        organization_id=row.organization_id,
        vendor_id=row.vendor_id,
        assessment_id=row.assessment_id,
        ai_assessment_id=row.ai_assessment_id,
        title=row.title,
        description=row.description,
        severity=row.severity,
        status=row.status,
        assigned_owner_id=row.assigned_owner_id,
        due_date=row.due_date,
        closed_at=row.closed_at,
        closed_by=row.closed_by,
        closure_notes=row.closure_notes,
        escalated_at=row.escalated_at,
        escalated_by=row.escalated_by,
        escalation_reason=row.escalation_reason,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
    )


def _action_read(row: VendorMitigationAction) -> VendorMitigationActionRead:
    return VendorMitigationActionRead(
        id=row.id,
        organization_id=row.organization_id,
        case_id=row.case_id,
        title=row.title,
        description=row.description,
        action_type=row.action_type,
        assigned_to_vendor=row.assigned_to_vendor,
        due_date=row.due_date,
        status=row.status,
        evidence_id=row.evidence_id,
        evidence_submitted_at=row.evidence_submitted_at,
        accepted_at=row.accepted_at,
        accepted_by=row.accepted_by,
        rejected_at=row.rejected_at,
        rejected_by=row.rejected_by,
        rejection_reason=row.rejection_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
    )


@router.post("/cases", response_model=VendorMitigationCaseRead, status_code=status.HTTP_201_CREATED)
def create_case(
    payload: VendorMitigationCaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> VendorMitigationCaseRead:
    row = VendorMitigationService(db).create_case(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _case_read(row)


@router.get("/cases", response_model=list[VendorMitigationCaseRead])
def list_cases(
    vendor_id: uuid.UUID | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    severity: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> list[VendorMitigationCaseRead]:
    rows = VendorMitigationService(db).list_cases(
        organization.id,
        vendor_id=vendor_id,
        status_value=status_value,
        severity=severity,
        skip=skip,
        limit=limit,
    )
    return [_case_read(row) for row in rows]


@router.get("/cases/summary", response_model=VendorMitigationSummary)
def mitigation_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> VendorMitigationSummary:
    return VendorMitigationSummary(**VendorMitigationService(db).get_mitigation_summary(organization.id))


@router.get("/cases/{case_id}", response_model=VendorMitigationCaseRead)
def get_case(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> VendorMitigationCaseRead:
    row = VendorMitigationService(db).get_case(organization.id, case_id)
    return _case_read(row)


@router.post("/cases/{case_id}/transition", response_model=VendorMitigationCaseRead)
def transition_case(
    case_id: uuid.UUID,
    payload: VendorMitigationCaseTransitionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> VendorMitigationCaseRead:
    row = VendorMitigationService(db).transition_case(
        organization.id,
        case_id,
        payload.new_status,
        current_user.id,
        notes=payload.notes,
    )
    db.commit()
    db.refresh(row)
    return _case_read(row)


@router.delete("/cases/{case_id}", response_model=VendorMitigationCaseRead)
def delete_case(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> VendorMitigationCaseRead:
    row = VendorMitigationService(db).soft_delete_case(organization.id, case_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _case_read(row)


@router.post("/cases/{case_id}/escalate", response_model=VendorMitigationCaseRead)
def escalate_case(
    case_id: uuid.UUID,
    payload: VendorMitigationCaseEscalateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> VendorMitigationCaseRead:
    row = VendorMitigationService(db).escalate_case(organization.id, case_id, current_user.id, payload.reason)
    db.commit()
    db.refresh(row)
    return _case_read(row)


@router.get("/cases/{case_id}/actions", response_model=list[VendorMitigationActionRead])
def list_actions(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> list[VendorMitigationActionRead]:
    rows = VendorMitigationService(db).list_actions(organization.id, case_id)
    return [_action_read(row) for row in rows]


@router.post("/cases/{case_id}/actions", response_model=VendorMitigationActionRead, status_code=status.HTTP_201_CREATED)
def add_action(
    case_id: uuid.UUID,
    payload: VendorMitigationActionCreate,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> VendorMitigationActionRead:
    row = VendorMitigationService(db).add_action(organization.id, case_id, payload)
    db.commit()
    db.refresh(row)
    return _action_read(row)


@router.post("/cases/{case_id}/actions/{action_id}/submit-evidence", response_model=VendorMitigationActionRead)
def submit_action_evidence(
    case_id: uuid.UUID,
    action_id: uuid.UUID,
    payload: VendorMitigationActionEvidenceSubmitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> VendorMitigationActionRead:
    row = VendorMitigationService(db).submit_action_evidence(
        organization.id,
        case_id,
        action_id,
        payload.evidence_id,
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _action_read(row)


@router.post("/cases/{case_id}/actions/{action_id}/accept", response_model=VendorMitigationActionRead)
def accept_action(
    case_id: uuid.UUID,
    action_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> VendorMitigationActionRead:
    row = VendorMitigationService(db).accept_action(organization.id, case_id, action_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _action_read(row)


@router.post("/cases/{case_id}/actions/{action_id}/reject", response_model=VendorMitigationActionRead)
def reject_action(
    case_id: uuid.UUID,
    action_id: uuid.UUID,
    payload: VendorMitigationActionRejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:write")),
) -> VendorMitigationActionRead:
    row = VendorMitigationService(db).reject_action(
        organization.id,
        case_id,
        action_id,
        current_user.id,
        payload.reason,
    )
    db.commit()
    db.refresh(row)
    return _action_read(row)
