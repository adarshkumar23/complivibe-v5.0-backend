import uuid

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.pam_session import (
    PAMSessionIngestRequest,
    PAMSessionIngestResponse,
    PAMSessionRead,
    PAMSessionUpdateRequest,
    PAMUnapprovedRiskSummary,
)
from app.services.pam_session_service import PAMSessionService

router = APIRouter(prefix="/pam/sessions", tags=["pam-sessions"])


@router.post("", response_model=PAMSessionIngestResponse, status_code=status.HTTP_201_CREATED)
def ingest_pam_session(
    payload: PAMSessionIngestRequest,
    db: Session = Depends(get_db),
    x_complivibe_key: str | None = Header(default=None, alias="X-CompliVibe-Key"),
) -> PAMSessionIngestResponse:
    # Shared inbound agent-push pattern: X-CompliVibe-Key resolves the org; no PAM outbound calls occur here.
    service = PAMSessionService(db)
    org_id = service.resolve_org_by_api_key(x_complivibe_key or "")
    row, created = service.ingest_session(org_id, payload)
    db.commit()
    db.refresh(row)
    return PAMSessionIngestResponse(
        session_id=row.id,
        external_session_id=row.external_session_id,
        approval_status=row.approval_status,
        risk_status=row.risk_status,
        risk_reason=row.risk_reason,
        created=created,
    )


@router.get("", response_model=list[PAMSessionRead])
def list_pam_sessions(
    approval_status: str | None = Query(default=None),
    risk_status: str | None = Query(default=None),
    identity: str | None = Query(default=None),
    target_system: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("technical_controls:view")),
) -> list[PAMSessionRead]:
    rows = PAMSessionService(db).list_sessions(
        organization.id,
        approval_status=approval_status,
        risk_status=risk_status,
        identity=identity,
        target_system=target_system,
        limit=limit,
    )
    return [PAMSessionRead.model_validate(row) for row in rows]


@router.get("/unapproved-risks", response_model=PAMUnapprovedRiskSummary)
def list_unapproved_pam_risks(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("technical_controls:view")),
) -> PAMUnapprovedRiskSummary:
    payload = PAMSessionService(db).list_unapproved_risks(organization.id, limit=limit)
    return PAMUnapprovedRiskSummary.model_validate(payload)


@router.post("/{session_id}/flag-unapproved", response_model=PAMSessionRead)
def flag_unapproved_pam_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("technical_controls:manage")),
) -> PAMSessionRead:
    row = PAMSessionService(db).flag_unapproved_session(organization.id, session_id, current_user.id)
    db.commit()
    db.refresh(row)
    return PAMSessionRead.model_validate(row)


@router.patch("/{session_id}", response_model=PAMSessionRead)
def update_pam_session(
    session_id: uuid.UUID,
    payload: PAMSessionUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("technical_controls:manage")),
) -> PAMSessionRead:
    row = PAMSessionService(db).update_session(organization.id, session_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return PAMSessionRead.model_validate(row)
