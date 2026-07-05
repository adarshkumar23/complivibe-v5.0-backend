import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.compliance.services.vendor_remediation_portal_service import VendorRemediationPortalService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.models.vendor import Vendor
from app.models.vendor_mitigation_action import VendorMitigationAction
from app.models.vendor_mitigation_case import VendorMitigationCase
from app.models.vendor_remediation_portal_token import VendorRemediationPortalToken
from app.schemas.vendor_remediation_portal import (
    VendorRemediationPortalActionRead,
    VendorRemediationPortalCaseRead,
    VendorRemediationPortalEvidenceSubmitRequest,
    VendorRemediationPortalEvidenceSubmitResponse,
    VendorRemediationPortalMeResponse,
    VendorRemediationPortalRevokeResponse,
    VendorRemediationPortalTokenCreate,
    VendorRemediationPortalTokenCreateResponse,
    VendorRemediationPortalTokenRead,
    VendorRemediationPortalVendorRead,
)

router = APIRouter(prefix="/vendor-remediation-portal", tags=["vendor-remediation-portal"])


def _token_read(row: VendorRemediationPortalToken) -> VendorRemediationPortalTokenRead:
    return VendorRemediationPortalTokenRead(
        id=row.id,
        organization_id=row.organization_id,
        vendor_id=row.vendor_id,
        case_id=row.case_id,
        vendor_contact_email=row.vendor_contact_email,
        vendor_contact_name=row.vendor_contact_name,
        masked_email=VendorRemediationPortalService.mask_email(row.vendor_contact_email),
        scoped_action_ids=[uuid.UUID(item) for item in row.scoped_action_ids] if row.scoped_action_ids is not None else None,
        expires_at=row.expires_at,
        first_accessed_at=row.first_accessed_at,
        last_accessed_at=row.last_accessed_at,
        access_count=row.access_count,
        status=row.status,
        revoked_at=row.revoked_at,
        revoked_by=row.revoked_by,
        created_by=row.created_by,
        created_at=row.created_at,
    )


def _vendor_read(row: Vendor) -> VendorRemediationPortalVendorRead:
    return VendorRemediationPortalVendorRead(
        id=row.id,
        name=row.name,
        primary_contact_name=row.primary_contact_name,
        primary_contact_email=row.primary_contact_email,
    )


def _case_read(row: VendorMitigationCase) -> VendorRemediationPortalCaseRead:
    return VendorRemediationPortalCaseRead(
        id=row.id,
        title=row.title,
        description=row.description,
        severity=row.severity,
        status=row.status,
        due_date=row.due_date,
    )


def _action_read(row: VendorMitigationAction) -> VendorRemediationPortalActionRead:
    return VendorRemediationPortalActionRead(
        id=row.id,
        case_id=row.case_id,
        title=row.title,
        description=row.description,
        action_type=row.action_type,
        due_date=row.due_date,
        status=row.status,
        evidence_id=row.evidence_id,
        evidence_submitted_at=row.evidence_submitted_at,
        rejection_reason=row.rejection_reason,
    )


def get_portal_token(
    authorization: str = Header(..., alias="Authorization"),
    db: Session = Depends(get_db),
) -> VendorRemediationPortalToken:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid portal token")
    raw_token = authorization.removeprefix("Bearer ").strip()
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid portal token")

    service = VendorRemediationPortalService(db)
    try:
        token = service.authenticate_portal_token(raw_token)
    except HTTPException:
        db.commit()
        raise

    db.commit()
    db.refresh(token)
    return token


@router.post("/tokens", response_model=VendorRemediationPortalTokenCreateResponse, status_code=status.HTTP_201_CREATED)
def create_token(
    payload: VendorRemediationPortalTokenCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor_remediation_portal:manage")),
) -> VendorRemediationPortalTokenCreateResponse:
    row, plaintext_token = VendorRemediationPortalService(db).create_token(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return VendorRemediationPortalTokenCreateResponse(
        token_id=row.id,
        vendor_id=row.vendor_id,
        case_id=row.case_id,
        vendor_contact_email=row.vendor_contact_email,
        expires_at=row.expires_at,
        plaintext_token=plaintext_token,
        warning="Token is shown only once. Store it securely.",
    )


@router.get("/tokens", response_model=list[VendorRemediationPortalTokenRead])
def list_tokens(
    vendor_id: uuid.UUID | None = Query(default=None),
    case_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor_remediation_portal:read")),
) -> list[VendorRemediationPortalTokenRead]:
    rows = VendorRemediationPortalService(db).list_tokens(organization.id, vendor_id=vendor_id, case_id=case_id)
    return [_token_read(row) for row in rows]


@router.get("/tokens/{token_id}", response_model=VendorRemediationPortalTokenRead)
def get_token(
    token_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor_remediation_portal:read")),
) -> VendorRemediationPortalTokenRead:
    row = VendorRemediationPortalService(db).get_token(organization.id, token_id)
    return _token_read(row)


@router.post("/tokens/{token_id}/revoke", response_model=VendorRemediationPortalRevokeResponse)
def revoke_token(
    token_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor_remediation_portal:manage")),
) -> VendorRemediationPortalRevokeResponse:
    row = VendorRemediationPortalService(db).revoke_token(organization.id, token_id, current_user.id)
    db.commit()
    db.refresh(row)
    return VendorRemediationPortalRevokeResponse(token_id=row.id, status=row.status)


@router.get("/me", response_model=VendorRemediationPortalMeResponse)
def portal_me(
    token: VendorRemediationPortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
) -> VendorRemediationPortalMeResponse:
    service = VendorRemediationPortalService(db)
    vendor = service.get_portal_vendor(token)
    case = service.get_portal_case(token)
    service.log_portal_view(token, "case_summary", [case.id])
    db.commit()

    return VendorRemediationPortalMeResponse(
        vendor_contact_email=token.vendor_contact_email,
        vendor=_vendor_read(vendor),
        case=_case_read(case),
        expires_at=token.expires_at,
        access_count=token.access_count,
    )


@router.get("/actions", response_model=list[VendorRemediationPortalActionRead])
def portal_actions(
    token: VendorRemediationPortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
) -> list[VendorRemediationPortalActionRead]:
    service = VendorRemediationPortalService(db)
    rows = service.get_portal_actions(token)
    service.log_portal_view(token, "actions", [row.id for row in rows])
    db.commit()
    return [_action_read(row) for row in rows]


@router.post("/actions/{action_id}/submit-evidence", response_model=VendorRemediationPortalEvidenceSubmitResponse)
def submit_action_evidence(
    action_id: uuid.UUID,
    payload: VendorRemediationPortalEvidenceSubmitRequest,
    token: VendorRemediationPortalToken = Depends(get_portal_token),
    db: Session = Depends(get_db),
) -> VendorRemediationPortalEvidenceSubmitResponse:
    row, evidence = VendorRemediationPortalService(db).submit_action_evidence(token, action_id, payload)
    db.commit()
    db.refresh(row)
    return VendorRemediationPortalEvidenceSubmitResponse(
        action=_action_read(row),
        evidence_id=evidence.id,
        message="Remediation evidence submitted for review.",
    )
