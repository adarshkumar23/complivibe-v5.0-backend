import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.services.auditor_portal_service import AuditorPortalService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.audit_engagement import AuditEngagement
from app.models.auditor_portal_invitation import AuditorPortalInvitation
from app.models.membership import Membership
from app.models.obligation import Obligation
from app.models.organization import Organization
from app.models.role import Role
from app.models.user import User
from app.schemas.auditor_portal import (
    AuditorPortalControlRead,
    AuditorPortalEvidenceRead,
    AuditorPortalInvitationCreate,
    AuditorPortalInvitationCreateResponse,
    AuditorPortalInvitationRead,
    AuditorPortalMeResponse,
    AuditorPortalReportRead,
    AuditorPortalRevokeResponse,
)
from app.services.evidence_service import EvidenceService

router = APIRouter(prefix="/audit-portal", tags=["auditor-portal"])


def _primary_framework_id(row: AuditorPortalInvitation) -> uuid.UUID | None:
    framework_ids = row.scoped_framework_ids or []
    if not framework_ids:
        return None
    return uuid.UUID(framework_ids[0])


def _invitation_read(row: AuditorPortalInvitation) -> AuditorPortalInvitationRead:
    return AuditorPortalInvitationRead(
        id=row.id,
        organization_id=row.organization_id,
        audit_engagement_id=row.audit_engagement_id,
        auditor_email=row.auditor_email,
        auditor_name=row.auditor_name,
        masked_email=AuditorPortalService.mask_email(row.auditor_email),
        framework_id=_primary_framework_id(row),
        scoped_framework_ids=[uuid.UUID(item) for item in (row.scoped_framework_ids or [])],
        scoped_control_ids=[uuid.UUID(item) for item in row.scoped_control_ids] if row.scoped_control_ids is not None else None,
        scoped_evidence_ids=[uuid.UUID(item) for item in row.scoped_evidence_ids] if row.scoped_evidence_ids is not None else None,
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


def _require_org_admin(db: Session, membership: Membership) -> None:
    role = db.execute(select(Role).where(Role.id == membership.role_id)).scalar_one_or_none()
    if role is None or role.name not in {"owner", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Org admin role required")


def get_portal_invitation(
    authorization: str = Header(..., alias="Authorization"),
    db: Session = Depends(get_db),
) -> AuditorPortalInvitation:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid portal token")

    raw_token = authorization.removeprefix("Bearer ").strip()
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid portal token")

    service = AuditorPortalService(db)
    try:
        invitation = service.authenticate_portal_token(raw_token)
    except HTTPException:
        db.commit()
        raise

    db.commit()
    db.refresh(invitation)
    return invitation


@router.post("/invitations", response_model=AuditorPortalInvitationCreateResponse, status_code=status.HTTP_201_CREATED)
def create_auditor_invitation(
    payload: AuditorPortalInvitationCreate,
    engagement_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("audit:write")),
) -> AuditorPortalInvitationCreateResponse:
    _require_org_admin(db, membership)
    row, plaintext_token = AuditorPortalService(db).create_invitation(organization.id, engagement_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return AuditorPortalInvitationCreateResponse(
        invitation_id=row.id,
        auditor_email=row.auditor_email,
        framework_id=_primary_framework_id(row),
        expires_at=row.expires_at,
        plaintext_token=plaintext_token,
        warning="Token is shown only once. Store it securely.",
    )


@router.get("/invitations", response_model=list[AuditorPortalInvitationRead])
def list_invitations(
    engagement_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:read")),
) -> list[AuditorPortalInvitationRead]:
    rows = AuditorPortalService(db).list_invitations(organization.id, engagement_id=engagement_id)
    return [_invitation_read(row) for row in rows]


@router.get("/invitations/{invitation_id}", response_model=AuditorPortalInvitationRead)
def get_invitation(
    invitation_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:read")),
) -> AuditorPortalInvitationRead:
    row = AuditorPortalService(db).get_invitation(organization.id, invitation_id)
    return _invitation_read(row)


@router.post("/invitations/{invitation_id}/revoke", response_model=AuditorPortalRevokeResponse)
def revoke_invitation(
    invitation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> AuditorPortalRevokeResponse:
    AuditorPortalService(db).revoke_invitation(organization.id, invitation_id, current_user.id)
    db.commit()
    row = AuditorPortalService(db).get_invitation(organization.id, invitation_id)
    return AuditorPortalRevokeResponse(invitation_id=row.id, status=row.status)


@router.get("/me", response_model=AuditorPortalMeResponse)
def portal_me(
    invitation: AuditorPortalInvitation = Depends(get_portal_invitation),
    db: Session = Depends(get_db),
) -> AuditorPortalMeResponse:
    engagement = db.execute(
        select(AuditEngagement).where(
            AuditEngagement.organization_id == invitation.organization_id,
            AuditEngagement.id == invitation.audit_engagement_id,
            AuditEngagement.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if engagement is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit engagement not found")

    AuditorPortalService(db).log_scoped_data_view(invitation, "engagement_summary", [invitation.audit_engagement_id])
    db.commit()
    invitation_scope = [uuid.UUID(item) for item in (invitation.scoped_framework_ids or [])]
    effective_scope = AuditorPortalService(db).effective_framework_ids(invitation)

    return AuditorPortalMeResponse(
        auditor_email=invitation.auditor_email,
        audit_engagement_title=engagement.title,
        expires_at=invitation.expires_at,
        scoped_framework_ids=invitation_scope,
        effective_framework_ids=effective_scope,
        scope_changed_since_invitation=set(invitation_scope) != set(effective_scope),
        access_count=invitation.access_count,
    )


@router.get("/controls", response_model=list[AuditorPortalControlRead])
def portal_controls(
    invitation: AuditorPortalInvitation = Depends(get_portal_invitation),
    db: Session = Depends(get_db),
) -> list[AuditorPortalControlRead]:
    rows = AuditorPortalService(db).get_scoped_controls(invitation)
    obligation_ids = [row.obligation_id for row in rows if row.obligation_id is not None]
    framework_by_obligation: dict[uuid.UUID, uuid.UUID] = {}
    if obligation_ids:
        for obligation in db.execute(select(Obligation).where(Obligation.id.in_(obligation_ids))).scalars().all():
            framework_by_obligation[obligation.id] = obligation.framework_id

    AuditorPortalService(db).log_scoped_data_view(invitation, "controls", [row.id for row in rows])
    db.commit()

    return [
        AuditorPortalControlRead(
            id=row.id,
            name=row.title,
            description=row.description,
            framework_id=framework_by_obligation.get(row.obligation_id) if row.obligation_id else None,
            status=row.status,
        )
        for row in rows
    ]


@router.get("/evidence", response_model=list[AuditorPortalEvidenceRead])
def portal_evidence(
    invitation: AuditorPortalInvitation = Depends(get_portal_invitation),
    db: Session = Depends(get_db),
) -> list[AuditorPortalEvidenceRead]:
    rows = AuditorPortalService(db).get_scoped_evidence(invitation)
    AuditorPortalService(db).log_scoped_data_view(invitation, "evidence", [row.id for row in rows])
    db.commit()

    return [
        AuditorPortalEvidenceRead(
            id=row.id,
            title=row.title,
            description=row.description,
            status=row.status,
            submitted_at=EvidenceService.effective_submitted_at(row),
            file_name=row.file_name,
            mime_type=row.mime_type,
            size_bytes=row.size_bytes,
            storage_provider=row.storage_provider,
            storage_key=row.storage_key,
        )
        for row in rows
    ]


@router.get("/reports", response_model=list[AuditorPortalReportRead])
def portal_reports(
    invitation: AuditorPortalInvitation = Depends(get_portal_invitation),
    db: Session = Depends(get_db),
) -> list[AuditorPortalReportRead]:
    rows = AuditorPortalService(db).get_scoped_reports(invitation)
    AuditorPortalService(db).log_scoped_data_view(invitation, "reports", [row.id for row in rows])
    db.commit()

    return [
        AuditorPortalReportRead(
            id=row.id,
            report_type=row.report_type,
            title=row.title,
            description=row.description,
            status=row.status,
            framework_id=row.framework_id,
            generated_at=row.generated_at,
        )
        for row in rows
    ]
