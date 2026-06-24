import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.ai_system import AISystem
from app.models.ai_system_control_link import AISystemControlLink
from app.models.ai_system_evidence_link import AISystemEvidenceLink
from app.models.ai_system_governance_attestation import AISystemGovernanceAttestation
from app.models.ai_system_governance_review_reminder_policy import AISystemGovernanceReviewReminderPolicy
from app.models.ai_system_governance_review import AISystemGovernanceReview
from app.models.ai_system_risk_link import AISystemRiskLink
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.ai_system import (
    AISystemArchiveRequest,
    AISystemControlLinkCreate,
    AISystemControlLinkRead,
    AISystemCreate,
    AISystemEvidenceLinkCreate,
    AISystemEvidenceLinkRead,
    AISystemGovernanceAttestationCreate,
    AISystemGovernanceAttestationRead,
    AISystemGovernanceAttestationVerifyResponse,
    AISystemGovernanceReviewCancel,
    AISystemGovernanceReviewComplete,
    AISystemGovernanceReviewCreate,
    AISystemGovernanceReviewRead,
    AISystemGovernanceReviewScheduleRequest,
    AISystemGovernanceSummary,
    AISystemLinksSummary,
    AISystemRead,
    AISystemRiskLinkCreate,
    AISystemRiskLinkRead,
    AISystemSummary,
    AISystemUnlinkRequest,
    AISystemUpdate,
)
from app.services.ai_system_service import AISystemService
from app.services.audit_service import AuditService

router = APIRouter(prefix="/ai-systems", tags=["ai_systems"])

AI_SYSTEM_GOVERNANCE_REVIEW_CAVEAT = (
    "This governance review is a manual internal CompliVibe governance checkpoint. "
    "It is not legal advice, regulatory approval, or certification."
)
AI_SYSTEM_GOVERNANCE_ATTESTATION_CAVEAT = (
    "This attestation uses an internal CompliVibe integrity signature. "
    "It is not a legal e-signature, external audit attestation, or certification."
)
AI_SYSTEM_GOVERNANCE_ATTESTATION_SIGNATURE_ALGORITHM = "HMAC-SHA256"


def _ai_system_read(row: AISystem) -> AISystemRead:
    return AISystemRead(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        description=row.description,
        system_type=row.system_type,
        lifecycle_status=row.lifecycle_status,
        deployment_environment=row.deployment_environment,
        business_owner_user_id=row.business_owner_user_id,
        technical_owner_user_id=row.technical_owner_user_id,
        vendor_name=row.vendor_name,
        provider_name=row.provider_name,
        model_name=row.model_name,
        model_version=row.model_version,
        intended_purpose=row.intended_purpose,
        use_case=row.use_case,
        data_categories_json=row.data_categories_json,
        user_groups_json=row.user_groups_json,
        geography_json=row.geography_json,
        tags_json=row.tags_json,
        notes=row.notes,
        created_by_user_id=row.created_by_user_id,
        updated_by_user_id=row.updated_by_user_id,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _control_link_read(row: AISystemControlLink) -> AISystemControlLinkRead:
    return AISystemControlLinkRead(
        id=row.id,
        organization_id=row.organization_id,
        ai_system_id=row.ai_system_id,
        control_id=row.control_id,
        status=row.status,
        link_reason=row.link_reason,
        created_by_user_id=row.created_by_user_id,
        unlinked_by_user_id=row.unlinked_by_user_id,
        unlinked_at=row.unlinked_at,
        unlink_reason=row.unlink_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _evidence_link_read(row: AISystemEvidenceLink) -> AISystemEvidenceLinkRead:
    return AISystemEvidenceLinkRead(
        id=row.id,
        organization_id=row.organization_id,
        ai_system_id=row.ai_system_id,
        evidence_id=row.evidence_id,
        status=row.status,
        link_reason=row.link_reason,
        created_by_user_id=row.created_by_user_id,
        unlinked_by_user_id=row.unlinked_by_user_id,
        unlinked_at=row.unlinked_at,
        unlink_reason=row.unlink_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _risk_link_read(row: AISystemRiskLink) -> AISystemRiskLinkRead:
    return AISystemRiskLinkRead(
        id=row.id,
        organization_id=row.organization_id,
        ai_system_id=row.ai_system_id,
        risk_id=row.risk_id,
        status=row.status,
        link_reason=row.link_reason,
        created_by_user_id=row.created_by_user_id,
        unlinked_by_user_id=row.unlinked_by_user_id,
        unlinked_at=row.unlinked_at,
        unlink_reason=row.unlink_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _governance_review_read(row: AISystemGovernanceReview) -> AISystemGovernanceReviewRead:
    return AISystemGovernanceReviewRead(
        id=row.id,
        organization_id=row.organization_id,
        ai_system_id=row.ai_system_id,
        review_type=row.review_type,
        status=row.status,
        outcome=row.outcome,
        title=row.title,
        description=row.description,
        checklist_json=row.checklist_json,
        findings_json=row.findings_json,
        conditions_json=row.conditions_json,
        requested_by_user_id=row.requested_by_user_id,
        assigned_to_user_id=row.assigned_to_user_id,
        started_by_user_id=row.started_by_user_id,
        started_at=row.started_at,
        completed_by_user_id=row.completed_by_user_id,
        completed_at=row.completed_at,
        cancelled_by_user_id=row.cancelled_by_user_id,
        cancelled_at=row.cancelled_at,
        cancellation_reason=row.cancellation_reason,
        caveat=row.caveat,
        due_at=row.due_at,
        reminder_policy_id=row.reminder_policy_id,
        last_reminder_at=row.last_reminder_at,
        escalated_at=row.escalated_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _governance_attestation_read(row: AISystemGovernanceAttestation) -> AISystemGovernanceAttestationRead:
    return AISystemGovernanceAttestationRead(
        id=row.id,
        organization_id=row.organization_id,
        ai_system_id=row.ai_system_id,
        review_id=row.review_id,
        signer_user_id=row.signer_user_id,
        signer_role_name=row.signer_role_name,
        decision=row.decision,
        statement=row.statement,
        checklist_snapshot_json=row.checklist_snapshot_json,
        review_snapshot_json=row.review_snapshot_json,
        content_sha256=row.content_sha256,
        signature_algorithm=row.signature_algorithm,
        internal_signature=row.internal_signature,
        signed_at=row.signed_at,
        caveat=row.caveat,
        created_at=row.created_at,
    )


def _governance_attestation_signature_payload(
    *,
    organization_id: uuid.UUID,
    ai_system_id: uuid.UUID,
    review_id: uuid.UUID,
    signer_user_id: uuid.UUID | None,
    signer_role_name: str | None,
    decision: str,
    statement: str,
    checklist_snapshot_json: dict | list | None,
    review_snapshot_json: dict | list | None,
    signed_at: datetime,
) -> dict:
    normalized_signed_at = signed_at if signed_at.tzinfo is not None else signed_at.replace(tzinfo=UTC)
    return {
        "organization_id": str(organization_id),
        "ai_system_id": str(ai_system_id),
        "review_id": str(review_id),
        "signer_user_id": str(signer_user_id) if signer_user_id else None,
        "signer_role_name": signer_role_name,
        "decision": decision,
        "statement": statement,
        "checklist_snapshot_json": checklist_snapshot_json,
        "review_snapshot_json": review_snapshot_json,
        "signed_at": normalized_signed_at.isoformat(),
    }


@router.post("", response_model=AISystemRead, status_code=status.HTTP_201_CREATED)
def create_ai_system(
    payload: AISystemCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRead:
    service = AISystemService(db)
    service.validate_owners(
        organization.id,
        business_owner_user_id=payload.business_owner_user_id,
        technical_owner_user_id=payload.technical_owner_user_id,
    )

    row = AISystem(
        organization_id=organization.id,
        name=payload.name,
        description=payload.description,
        system_type=payload.system_type,
        lifecycle_status=payload.lifecycle_status,
        deployment_environment=payload.deployment_environment,
        business_owner_user_id=payload.business_owner_user_id,
        technical_owner_user_id=payload.technical_owner_user_id,
        vendor_name=payload.vendor_name,
        provider_name=payload.provider_name,
        model_name=payload.model_name,
        model_version=payload.model_version,
        intended_purpose=payload.intended_purpose,
        use_case=payload.use_case,
        data_categories_json=payload.data_categories_json,
        user_groups_json=payload.user_groups_json,
        geography_json=payload.geography_json,
        tags_json=payload.tags_json,
        notes=payload.notes,
        created_by_user_id=current_user.id,
        updated_by_user_id=current_user.id,
    )
    db.add(row)
    db.flush()

    AuditService(db).write_audit_log(
        action="ai_system.created",
        entity_type="ai_system",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "name": row.name,
            "system_type": row.system_type,
            "lifecycle_status": row.lifecycle_status,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _ai_system_read(row)


@router.post("/{ai_system_id}/links/controls", response_model=AISystemControlLinkRead, status_code=status.HTTP_201_CREATED)
def link_control_to_ai_system(
    ai_system_id: uuid.UUID,
    payload: AISystemControlLinkCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemControlLinkRead:
    service = AISystemService(db)
    row = service.require_ai_system_in_org(organization.id, ai_system_id)
    service.ensure_ai_system_linkable(row)
    service.require_control_in_org(organization.id, payload.control_id)

    link = db.execute(
        select(AISystemControlLink).where(
            AISystemControlLink.organization_id == organization.id,
            AISystemControlLink.ai_system_id == row.id,
            AISystemControlLink.control_id == payload.control_id,
        )
    ).scalar_one_or_none()

    if link is not None and link.status == "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active AI system-control link already exists")

    if link is None:
        link = AISystemControlLink(
            organization_id=organization.id,
            ai_system_id=row.id,
            control_id=payload.control_id,
            status="active",
            link_reason=payload.link_reason,
            created_by_user_id=current_user.id,
        )
        db.add(link)
    else:
        link.status = "active"
        link.link_reason = payload.link_reason
        link.unlinked_at = None
        link.unlink_reason = None
        link.unlinked_by_user_id = None
    db.flush()

    AuditService(db).write_audit_log(
        action="ai_system.control_linked",
        entity_type="ai_system_control_link",
        entity_id=link.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "ai_system_id": str(row.id),
            "control_id": str(payload.control_id),
            "status": link.status,
        },
        metadata_json={"source": "api", "link_reason": payload.link_reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(link)
    return _control_link_read(link)


@router.get("/{ai_system_id}/links/controls", response_model=list[AISystemControlLinkRead])
def list_ai_system_control_links(
    ai_system_id: uuid.UUID,
    include_unlinked: bool = Query(default=False),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemControlLinkRead]:
    service = AISystemService(db)
    row = service.require_ai_system_in_org(organization.id, ai_system_id)
    stmt = select(AISystemControlLink).where(
        AISystemControlLink.organization_id == organization.id,
        AISystemControlLink.ai_system_id == row.id,
    )
    if not include_unlinked:
        stmt = stmt.where(AISystemControlLink.status == "active")
    stmt = stmt.order_by(AISystemControlLink.created_at.desc())
    links = db.execute(stmt).scalars().all()
    return [_control_link_read(link) for link in links]


@router.post("/{ai_system_id}/links/controls/{link_id}/unlink", response_model=AISystemControlLinkRead)
def unlink_control_from_ai_system(
    ai_system_id: uuid.UUID,
    link_id: uuid.UUID,
    payload: AISystemUnlinkRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemControlLinkRead:
    service = AISystemService(db)
    row = service.require_ai_system_in_org(organization.id, ai_system_id)
    link = db.execute(
        select(AISystemControlLink).where(
            AISystemControlLink.id == link_id,
            AISystemControlLink.organization_id == organization.id,
            AISystemControlLink.ai_system_id == row.id,
        )
    ).scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system-control link not found")
    if link.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI system-control link is not active")

    before = {"status": link.status}
    link.status = "unlinked"
    link.unlinked_by_user_id = current_user.id
    link.unlinked_at = datetime.now(UTC)
    link.unlink_reason = payload.unlink_reason
    db.flush()

    AuditService(db).write_audit_log(
        action="ai_system.control_unlinked",
        entity_type="ai_system_control_link",
        entity_id=link.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": link.status, "control_id": str(link.control_id)},
        metadata_json={"source": "api", "unlink_reason": payload.unlink_reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(link)
    return _control_link_read(link)


@router.post("/{ai_system_id}/links/evidence", response_model=AISystemEvidenceLinkRead, status_code=status.HTTP_201_CREATED)
def link_evidence_to_ai_system(
    ai_system_id: uuid.UUID,
    payload: AISystemEvidenceLinkCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemEvidenceLinkRead:
    service = AISystemService(db)
    row = service.require_ai_system_in_org(organization.id, ai_system_id)
    service.ensure_ai_system_linkable(row)
    service.require_evidence_in_org(organization.id, payload.evidence_id)

    link = db.execute(
        select(AISystemEvidenceLink).where(
            AISystemEvidenceLink.organization_id == organization.id,
            AISystemEvidenceLink.ai_system_id == row.id,
            AISystemEvidenceLink.evidence_id == payload.evidence_id,
        )
    ).scalar_one_or_none()

    if link is not None and link.status == "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active AI system-evidence link already exists")

    if link is None:
        link = AISystemEvidenceLink(
            organization_id=organization.id,
            ai_system_id=row.id,
            evidence_id=payload.evidence_id,
            status="active",
            link_reason=payload.link_reason,
            created_by_user_id=current_user.id,
        )
        db.add(link)
    else:
        link.status = "active"
        link.link_reason = payload.link_reason
        link.unlinked_at = None
        link.unlink_reason = None
        link.unlinked_by_user_id = None
    db.flush()

    AuditService(db).write_audit_log(
        action="ai_system.evidence_linked",
        entity_type="ai_system_evidence_link",
        entity_id=link.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "ai_system_id": str(row.id),
            "evidence_id": str(payload.evidence_id),
            "status": link.status,
        },
        metadata_json={"source": "api", "link_reason": payload.link_reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(link)
    return _evidence_link_read(link)


@router.get("/{ai_system_id}/links/evidence", response_model=list[AISystemEvidenceLinkRead])
def list_ai_system_evidence_links(
    ai_system_id: uuid.UUID,
    include_unlinked: bool = Query(default=False),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemEvidenceLinkRead]:
    service = AISystemService(db)
    row = service.require_ai_system_in_org(organization.id, ai_system_id)
    stmt = select(AISystemEvidenceLink).where(
        AISystemEvidenceLink.organization_id == organization.id,
        AISystemEvidenceLink.ai_system_id == row.id,
    )
    if not include_unlinked:
        stmt = stmt.where(AISystemEvidenceLink.status == "active")
    stmt = stmt.order_by(AISystemEvidenceLink.created_at.desc())
    links = db.execute(stmt).scalars().all()
    return [_evidence_link_read(link) for link in links]


@router.post("/{ai_system_id}/links/evidence/{link_id}/unlink", response_model=AISystemEvidenceLinkRead)
def unlink_evidence_from_ai_system(
    ai_system_id: uuid.UUID,
    link_id: uuid.UUID,
    payload: AISystemUnlinkRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemEvidenceLinkRead:
    service = AISystemService(db)
    row = service.require_ai_system_in_org(organization.id, ai_system_id)
    link = db.execute(
        select(AISystemEvidenceLink).where(
            AISystemEvidenceLink.id == link_id,
            AISystemEvidenceLink.organization_id == organization.id,
            AISystemEvidenceLink.ai_system_id == row.id,
        )
    ).scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system-evidence link not found")
    if link.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI system-evidence link is not active")

    before = {"status": link.status}
    link.status = "unlinked"
    link.unlinked_by_user_id = current_user.id
    link.unlinked_at = datetime.now(UTC)
    link.unlink_reason = payload.unlink_reason
    db.flush()

    AuditService(db).write_audit_log(
        action="ai_system.evidence_unlinked",
        entity_type="ai_system_evidence_link",
        entity_id=link.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": link.status, "evidence_id": str(link.evidence_id)},
        metadata_json={"source": "api", "unlink_reason": payload.unlink_reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(link)
    return _evidence_link_read(link)


@router.post("/{ai_system_id}/links/risks", response_model=AISystemRiskLinkRead, status_code=status.HTTP_201_CREATED)
def link_risk_to_ai_system(
    ai_system_id: uuid.UUID,
    payload: AISystemRiskLinkCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskLinkRead:
    service = AISystemService(db)
    row = service.require_ai_system_in_org(organization.id, ai_system_id)
    service.ensure_ai_system_linkable(row)
    service.require_risk_in_org(organization.id, payload.risk_id)

    link = db.execute(
        select(AISystemRiskLink).where(
            AISystemRiskLink.organization_id == organization.id,
            AISystemRiskLink.ai_system_id == row.id,
            AISystemRiskLink.risk_id == payload.risk_id,
        )
    ).scalar_one_or_none()

    if link is not None and link.status == "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active AI system-risk link already exists")

    if link is None:
        link = AISystemRiskLink(
            organization_id=organization.id,
            ai_system_id=row.id,
            risk_id=payload.risk_id,
            status="active",
            link_reason=payload.link_reason,
            created_by_user_id=current_user.id,
        )
        db.add(link)
    else:
        link.status = "active"
        link.link_reason = payload.link_reason
        link.unlinked_at = None
        link.unlink_reason = None
        link.unlinked_by_user_id = None
    db.flush()

    AuditService(db).write_audit_log(
        action="ai_system.risk_linked",
        entity_type="ai_system_risk_link",
        entity_id=link.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "ai_system_id": str(row.id),
            "risk_id": str(payload.risk_id),
            "status": link.status,
        },
        metadata_json={"source": "api", "link_reason": payload.link_reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(link)
    return _risk_link_read(link)


@router.get("/{ai_system_id}/links/risks", response_model=list[AISystemRiskLinkRead])
def list_ai_system_risk_links(
    ai_system_id: uuid.UUID,
    include_unlinked: bool = Query(default=False),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemRiskLinkRead]:
    service = AISystemService(db)
    row = service.require_ai_system_in_org(organization.id, ai_system_id)
    stmt = select(AISystemRiskLink).where(
        AISystemRiskLink.organization_id == organization.id,
        AISystemRiskLink.ai_system_id == row.id,
    )
    if not include_unlinked:
        stmt = stmt.where(AISystemRiskLink.status == "active")
    stmt = stmt.order_by(AISystemRiskLink.created_at.desc())
    links = db.execute(stmt).scalars().all()
    return [_risk_link_read(link) for link in links]


@router.post("/{ai_system_id}/links/risks/{link_id}/unlink", response_model=AISystemRiskLinkRead)
def unlink_risk_from_ai_system(
    ai_system_id: uuid.UUID,
    link_id: uuid.UUID,
    payload: AISystemUnlinkRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskLinkRead:
    service = AISystemService(db)
    row = service.require_ai_system_in_org(organization.id, ai_system_id)
    link = db.execute(
        select(AISystemRiskLink).where(
            AISystemRiskLink.id == link_id,
            AISystemRiskLink.organization_id == organization.id,
            AISystemRiskLink.ai_system_id == row.id,
        )
    ).scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system-risk link not found")
    if link.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI system-risk link is not active")

    before = {"status": link.status}
    link.status = "unlinked"
    link.unlinked_by_user_id = current_user.id
    link.unlinked_at = datetime.now(UTC)
    link.unlink_reason = payload.unlink_reason
    db.flush()

    AuditService(db).write_audit_log(
        action="ai_system.risk_unlinked",
        entity_type="ai_system_risk_link",
        entity_id=link.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": link.status, "risk_id": str(link.risk_id)},
        metadata_json={"source": "api", "unlink_reason": payload.unlink_reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(link)
    return _risk_link_read(link)


@router.get("/{ai_system_id}/links/summary", response_model=AISystemLinksSummary)
def ai_system_links_summary(
    ai_system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemLinksSummary:
    row = AISystemService(db).require_ai_system_in_org(organization.id, ai_system_id)
    active_control_links = int(
        db.execute(
            select(func.count(AISystemControlLink.id)).where(
                AISystemControlLink.organization_id == organization.id,
                AISystemControlLink.ai_system_id == row.id,
                AISystemControlLink.status == "active",
            )
        ).scalar_one()
    )
    unlinked_control_links = int(
        db.execute(
            select(func.count(AISystemControlLink.id)).where(
                AISystemControlLink.organization_id == organization.id,
                AISystemControlLink.ai_system_id == row.id,
                AISystemControlLink.status == "unlinked",
            )
        ).scalar_one()
    )
    active_evidence_links = int(
        db.execute(
            select(func.count(AISystemEvidenceLink.id)).where(
                AISystemEvidenceLink.organization_id == organization.id,
                AISystemEvidenceLink.ai_system_id == row.id,
                AISystemEvidenceLink.status == "active",
            )
        ).scalar_one()
    )
    unlinked_evidence_links = int(
        db.execute(
            select(func.count(AISystemEvidenceLink.id)).where(
                AISystemEvidenceLink.organization_id == organization.id,
                AISystemEvidenceLink.ai_system_id == row.id,
                AISystemEvidenceLink.status == "unlinked",
            )
        ).scalar_one()
    )
    active_risk_links = int(
        db.execute(
            select(func.count(AISystemRiskLink.id)).where(
                AISystemRiskLink.organization_id == organization.id,
                AISystemRiskLink.ai_system_id == row.id,
                AISystemRiskLink.status == "active",
            )
        ).scalar_one()
    )
    unlinked_risk_links = int(
        db.execute(
            select(func.count(AISystemRiskLink.id)).where(
                AISystemRiskLink.organization_id == organization.id,
                AISystemRiskLink.ai_system_id == row.id,
                AISystemRiskLink.status == "unlinked",
            )
        ).scalar_one()
    )
    return AISystemLinksSummary(
        active_control_links=active_control_links,
        active_evidence_links=active_evidence_links,
        active_risk_links=active_risk_links,
        unlinked_control_links=unlinked_control_links,
        unlinked_evidence_links=unlinked_evidence_links,
        unlinked_risk_links=unlinked_risk_links,
        total_active_links=active_control_links + active_evidence_links + active_risk_links,
        total_unlinked_links=unlinked_control_links + unlinked_evidence_links + unlinked_risk_links,
    )


@router.post(
    "/{ai_system_id}/governance-reviews",
    response_model=AISystemGovernanceReviewRead,
    status_code=status.HTTP_201_CREATED,
)
def create_ai_system_governance_review(
    ai_system_id: uuid.UUID,
    payload: AISystemGovernanceReviewCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceReviewRead:
    service = AISystemService(db)
    ai_system = service.require_ai_system_in_org(organization.id, ai_system_id)
    if ai_system.lifecycle_status == "archived" and payload.review_type != "retirement_review":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Archived AI systems only allow retirement_review governance reviews",
        )
    if payload.assigned_to_user_id is not None:
        service.ensure_active_member(
            organization.id,
            payload.assigned_to_user_id,
            field_name="assigned_to_user_id",
        )

    row = AISystemGovernanceReview(
        organization_id=organization.id,
        ai_system_id=ai_system.id,
        review_type=payload.review_type,
        status="pending",
        outcome=None,
        title=payload.title,
        description=payload.description,
        checklist_json=payload.checklist_json,
        requested_by_user_id=current_user.id,
        assigned_to_user_id=payload.assigned_to_user_id,
        caveat=AI_SYSTEM_GOVERNANCE_REVIEW_CAVEAT,
    )
    db.add(row)
    db.flush()

    AuditService(db).write_audit_log(
        action="ai_system_governance_review.created",
        entity_type="ai_system_governance_review",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "ai_system_id": str(ai_system.id),
            "review_type": row.review_type,
            "status": row.status,
            "assigned_to_user_id": str(row.assigned_to_user_id) if row.assigned_to_user_id else None,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_review_read(row)


@router.get("/{ai_system_id}/governance-reviews", response_model=list[AISystemGovernanceReviewRead])
def list_ai_system_governance_reviews(
    ai_system_id: uuid.UUID,
    status_filter: str | None = Query(default=None, alias="status"),
    review_type: str | None = Query(default=None),
    outcome: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernanceReviewRead]:
    ai_system = AISystemService(db).require_ai_system_in_org(organization.id, ai_system_id)
    stmt = select(AISystemGovernanceReview).where(
        AISystemGovernanceReview.organization_id == organization.id,
        AISystemGovernanceReview.ai_system_id == ai_system.id,
    )
    if status_filter:
        stmt = stmt.where(AISystemGovernanceReview.status == status_filter)
    if review_type:
        stmt = stmt.where(AISystemGovernanceReview.review_type == review_type)
    if outcome:
        stmt = stmt.where(AISystemGovernanceReview.outcome == outcome)
    stmt = stmt.order_by(AISystemGovernanceReview.created_at.desc()).offset(offset).limit(limit)
    rows = db.execute(stmt).scalars().all()
    return [_governance_review_read(row) for row in rows]


@router.get(
    "/{ai_system_id}/governance-reviews/{review_id}",
    response_model=AISystemGovernanceReviewRead,
)
def get_ai_system_governance_review(
    ai_system_id: uuid.UUID,
    review_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceReviewRead:
    ai_system = AISystemService(db).require_ai_system_in_org(organization.id, ai_system_id)
    row = db.execute(
        select(AISystemGovernanceReview).where(
            AISystemGovernanceReview.id == review_id,
            AISystemGovernanceReview.organization_id == organization.id,
            AISystemGovernanceReview.ai_system_id == ai_system.id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system governance review not found")
    return _governance_review_read(row)


@router.post(
    "/{ai_system_id}/governance-reviews/{review_id}/schedule",
    response_model=AISystemGovernanceReviewRead,
)
def schedule_ai_system_governance_review(
    ai_system_id: uuid.UUID,
    review_id: uuid.UUID,
    payload: AISystemGovernanceReviewScheduleRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceReviewRead:
    ai_system = AISystemService(db).require_ai_system_in_org(organization.id, ai_system_id)
    review = db.execute(
        select(AISystemGovernanceReview).where(
            AISystemGovernanceReview.id == review_id,
            AISystemGovernanceReview.organization_id == organization.id,
            AISystemGovernanceReview.ai_system_id == ai_system.id,
        )
    ).scalar_one_or_none()
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system governance review not found")
    if review.status not in {"pending", "in_progress"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only pending or in_progress governance reviews can be scheduled",
        )
    if payload.reminder_policy_id is not None:
        policy = db.execute(
            select(AISystemGovernanceReviewReminderPolicy).where(
                AISystemGovernanceReviewReminderPolicy.id == payload.reminder_policy_id,
                AISystemGovernanceReviewReminderPolicy.organization_id == organization.id,
            )
        ).scalar_one_or_none()
        if policy is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="AI governance review reminder policy not found",
            )
        if policy.status != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reminder policy must be active",
            )

    before = {
        "due_at": review.due_at.isoformat() if review.due_at else None,
        "reminder_policy_id": str(review.reminder_policy_id) if review.reminder_policy_id else None,
        "last_reminder_at": review.last_reminder_at.isoformat() if review.last_reminder_at else None,
        "escalated_at": review.escalated_at.isoformat() if review.escalated_at else None,
    }

    review.due_at = payload.due_at
    review.reminder_policy_id = payload.reminder_policy_id
    review.last_reminder_at = None
    review.escalated_at = None
    db.flush()

    AuditService(db).write_audit_log(
        action="ai_system_governance_review.scheduled",
        entity_type="ai_system_governance_review",
        entity_id=review.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "due_at": review.due_at.isoformat() if review.due_at else None,
            "reminder_policy_id": str(review.reminder_policy_id) if review.reminder_policy_id else None,
            "last_reminder_at": review.last_reminder_at.isoformat() if review.last_reminder_at else None,
            "escalated_at": review.escalated_at.isoformat() if review.escalated_at else None,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(review)
    return _governance_review_read(review)


@router.post(
    "/{ai_system_id}/governance-reviews/{review_id}/start",
    response_model=AISystemGovernanceReviewRead,
)
def start_ai_system_governance_review(
    ai_system_id: uuid.UUID,
    review_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceReviewRead:
    ai_system = AISystemService(db).require_ai_system_in_org(organization.id, ai_system_id)
    row = db.execute(
        select(AISystemGovernanceReview).where(
            AISystemGovernanceReview.id == review_id,
            AISystemGovernanceReview.organization_id == organization.id,
            AISystemGovernanceReview.ai_system_id == ai_system.id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system governance review not found")
    if row.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Governance review must be pending to start")

    row.status = "in_progress"
    row.started_by_user_id = current_user.id
    row.started_at = datetime.now(UTC)
    db.flush()

    AuditService(db).write_audit_log(
        action="ai_system_governance_review.started",
        entity_type="ai_system_governance_review",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "ai_system_id": str(ai_system.id),
            "status": row.status,
            "started_at": row.started_at.isoformat() if row.started_at else None,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_review_read(row)


@router.post(
    "/{ai_system_id}/governance-reviews/{review_id}/complete",
    response_model=AISystemGovernanceReviewRead,
)
def complete_ai_system_governance_review(
    ai_system_id: uuid.UUID,
    review_id: uuid.UUID,
    payload: AISystemGovernanceReviewComplete,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceReviewRead:
    ai_system = AISystemService(db).require_ai_system_in_org(organization.id, ai_system_id)
    row = db.execute(
        select(AISystemGovernanceReview).where(
            AISystemGovernanceReview.id == review_id,
            AISystemGovernanceReview.organization_id == organization.id,
            AISystemGovernanceReview.ai_system_id == ai_system.id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system governance review not found")
    if row.status not in {"pending", "in_progress"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Governance review must be pending or in_progress to complete",
        )

    row.status = "completed"
    row.outcome = payload.outcome
    row.findings_json = payload.findings_json
    row.conditions_json = payload.conditions_json
    if payload.checklist_json is not None:
        row.checklist_json = payload.checklist_json
    row.completed_by_user_id = current_user.id
    row.completed_at = datetime.now(UTC)
    db.flush()

    AuditService(db).write_audit_log(
        action="ai_system_governance_review.completed",
        entity_type="ai_system_governance_review",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "ai_system_id": str(ai_system.id),
            "status": row.status,
            "outcome": row.outcome,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_review_read(row)


@router.post(
    "/{ai_system_id}/governance-reviews/{review_id}/cancel",
    response_model=AISystemGovernanceReviewRead,
)
def cancel_ai_system_governance_review(
    ai_system_id: uuid.UUID,
    review_id: uuid.UUID,
    payload: AISystemGovernanceReviewCancel,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceReviewRead:
    ai_system = AISystemService(db).require_ai_system_in_org(organization.id, ai_system_id)
    row = db.execute(
        select(AISystemGovernanceReview).where(
            AISystemGovernanceReview.id == review_id,
            AISystemGovernanceReview.organization_id == organization.id,
            AISystemGovernanceReview.ai_system_id == ai_system.id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system governance review not found")
    if row.status == "completed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Completed governance reviews cannot be cancelled")
    if row.status == "cancelled":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Governance review is already cancelled")

    row.status = "cancelled"
    row.cancelled_by_user_id = current_user.id
    row.cancelled_at = datetime.now(UTC)
    row.cancellation_reason = payload.cancellation_reason
    db.flush()

    AuditService(db).write_audit_log(
        action="ai_system_governance_review.cancelled",
        entity_type="ai_system_governance_review",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "ai_system_id": str(ai_system.id),
            "status": row.status,
            "cancelled_at": row.cancelled_at.isoformat() if row.cancelled_at else None,
        },
        metadata_json={"source": "api", "cancellation_reason": payload.cancellation_reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_review_read(row)


@router.post(
    "/{ai_system_id}/governance-reviews/{review_id}/attestations",
    response_model=AISystemGovernanceAttestationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_ai_system_governance_attestation(
    ai_system_id: uuid.UUID,
    review_id: uuid.UUID,
    payload: AISystemGovernanceAttestationCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceAttestationRead:
    service = AISystemService(db)
    ai_system = service.require_ai_system_in_org(organization.id, ai_system_id)
    review = db.execute(
        select(AISystemGovernanceReview).where(
            AISystemGovernanceReview.id == review_id,
            AISystemGovernanceReview.organization_id == organization.id,
            AISystemGovernanceReview.ai_system_id == ai_system.id,
        )
    ).scalar_one_or_none()
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system governance review not found")
    if review.status != "completed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attestation requires completed governance review")

    existing = db.execute(
        select(AISystemGovernanceAttestation).where(
            AISystemGovernanceAttestation.organization_id == organization.id,
            AISystemGovernanceAttestation.review_id == review.id,
            AISystemGovernanceAttestation.signer_user_id == current_user.id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Signer has already attested this governance review",
        )

    signer_role_name = service.signer_role_name(organization.id, current_user.id)
    signed_at = datetime.now(UTC)
    review_snapshot_json = _governance_review_read(review).model_dump(mode="json")
    checklist_snapshot_json = review.checklist_json
    signature_payload = _governance_attestation_signature_payload(
        organization_id=organization.id,
        ai_system_id=ai_system.id,
        review_id=review.id,
        signer_user_id=current_user.id,
        signer_role_name=signer_role_name,
        decision=payload.decision,
        statement=payload.statement,
        checklist_snapshot_json=checklist_snapshot_json,
        review_snapshot_json=review_snapshot_json,
        signed_at=signed_at,
    )
    content_sha256 = service.sha256_hexdigest(signature_payload)
    internal_signature = service.hmac_signature(content_sha256)

    row = AISystemGovernanceAttestation(
        organization_id=organization.id,
        ai_system_id=ai_system.id,
        review_id=review.id,
        signer_user_id=current_user.id,
        signer_role_name=signer_role_name,
        decision=payload.decision,
        statement=payload.statement,
        checklist_snapshot_json=checklist_snapshot_json,
        review_snapshot_json=review_snapshot_json,
        content_sha256=content_sha256,
        signature_algorithm=AI_SYSTEM_GOVERNANCE_ATTESTATION_SIGNATURE_ALGORITHM,
        internal_signature=internal_signature,
        signed_at=signed_at,
        caveat=AI_SYSTEM_GOVERNANCE_ATTESTATION_CAVEAT,
    )
    db.add(row)
    db.flush()

    AuditService(db).write_audit_log(
        action="ai_system_governance_attestation.created",
        entity_type="ai_system_governance_attestation",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "ai_system_id": str(ai_system.id),
            "review_id": str(review.id),
            "decision": row.decision,
            "signature_algorithm": row.signature_algorithm,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_attestation_read(row)


@router.get(
    "/{ai_system_id}/governance-reviews/{review_id}/attestations",
    response_model=list[AISystemGovernanceAttestationRead],
)
def list_ai_system_governance_attestations(
    ai_system_id: uuid.UUID,
    review_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernanceAttestationRead]:
    ai_system = AISystemService(db).require_ai_system_in_org(organization.id, ai_system_id)
    review = db.execute(
        select(AISystemGovernanceReview).where(
            AISystemGovernanceReview.id == review_id,
            AISystemGovernanceReview.organization_id == organization.id,
            AISystemGovernanceReview.ai_system_id == ai_system.id,
        )
    ).scalar_one_or_none()
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system governance review not found")
    rows = db.execute(
        select(AISystemGovernanceAttestation)
        .where(
            AISystemGovernanceAttestation.organization_id == organization.id,
            AISystemGovernanceAttestation.ai_system_id == ai_system.id,
            AISystemGovernanceAttestation.review_id == review.id,
        )
        .order_by(AISystemGovernanceAttestation.created_at.desc())
    ).scalars().all()
    return [_governance_attestation_read(row) for row in rows]


@router.post(
    "/{ai_system_id}/governance-reviews/{review_id}/attestations/{attestation_id}/verify",
    response_model=AISystemGovernanceAttestationVerifyResponse,
)
def verify_ai_system_governance_attestation(
    ai_system_id: uuid.UUID,
    review_id: uuid.UUID,
    attestation_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceAttestationVerifyResponse:
    service = AISystemService(db)
    ai_system = service.require_ai_system_in_org(organization.id, ai_system_id)
    review = db.execute(
        select(AISystemGovernanceReview).where(
            AISystemGovernanceReview.id == review_id,
            AISystemGovernanceReview.organization_id == organization.id,
            AISystemGovernanceReview.ai_system_id == ai_system.id,
        )
    ).scalar_one_or_none()
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system governance review not found")

    row = db.execute(
        select(AISystemGovernanceAttestation).where(
            AISystemGovernanceAttestation.id == attestation_id,
            AISystemGovernanceAttestation.organization_id == organization.id,
            AISystemGovernanceAttestation.ai_system_id == ai_system.id,
            AISystemGovernanceAttestation.review_id == review.id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system governance attestation not found")

    signature_payload = _governance_attestation_signature_payload(
        organization_id=row.organization_id,
        ai_system_id=row.ai_system_id,
        review_id=row.review_id,
        signer_user_id=row.signer_user_id,
        signer_role_name=row.signer_role_name,
        decision=row.decision,
        statement=row.statement,
        checklist_snapshot_json=row.checklist_snapshot_json,
        review_snapshot_json=row.review_snapshot_json,
        signed_at=row.signed_at,
    )
    recomputed_sha256 = service.sha256_hexdigest(signature_payload)
    recomputed_signature = service.hmac_signature(recomputed_sha256)
    valid_hash = row.content_sha256 == recomputed_sha256
    valid_signature = row.internal_signature == recomputed_signature

    return AISystemGovernanceAttestationVerifyResponse(
        valid_hash=valid_hash,
        valid_signature=valid_signature,
        content_sha256=row.content_sha256,
        recomputed_sha256=recomputed_sha256,
        signature_algorithm=row.signature_algorithm,
        caveat=AI_SYSTEM_GOVERNANCE_ATTESTATION_CAVEAT,
    )


@router.get("/{ai_system_id}/governance-summary", response_model=AISystemGovernanceSummary)
def ai_system_governance_summary(
    ai_system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceSummary:
    ai_system = AISystemService(db).require_ai_system_in_org(organization.id, ai_system_id)
    total_reviews = int(
        db.execute(
            select(func.count(AISystemGovernanceReview.id)).where(
                AISystemGovernanceReview.organization_id == organization.id,
                AISystemGovernanceReview.ai_system_id == ai_system.id,
            )
        ).scalar_one()
    )
    pending_reviews = int(
        db.execute(
            select(func.count(AISystemGovernanceReview.id)).where(
                AISystemGovernanceReview.organization_id == organization.id,
                AISystemGovernanceReview.ai_system_id == ai_system.id,
                AISystemGovernanceReview.status == "pending",
            )
        ).scalar_one()
    )
    in_progress_reviews = int(
        db.execute(
            select(func.count(AISystemGovernanceReview.id)).where(
                AISystemGovernanceReview.organization_id == organization.id,
                AISystemGovernanceReview.ai_system_id == ai_system.id,
                AISystemGovernanceReview.status == "in_progress",
            )
        ).scalar_one()
    )
    completed_reviews = int(
        db.execute(
            select(func.count(AISystemGovernanceReview.id)).where(
                AISystemGovernanceReview.organization_id == organization.id,
                AISystemGovernanceReview.ai_system_id == ai_system.id,
                AISystemGovernanceReview.status == "completed",
            )
        ).scalar_one()
    )
    cancelled_reviews = int(
        db.execute(
            select(func.count(AISystemGovernanceReview.id)).where(
                AISystemGovernanceReview.organization_id == organization.id,
                AISystemGovernanceReview.ai_system_id == ai_system.id,
                AISystemGovernanceReview.status == "cancelled",
            )
        ).scalar_one()
    )
    by_review_type_rows = db.execute(
        select(AISystemGovernanceReview.review_type, func.count(AISystemGovernanceReview.id))
        .where(
            AISystemGovernanceReview.organization_id == organization.id,
            AISystemGovernanceReview.ai_system_id == ai_system.id,
        )
        .group_by(AISystemGovernanceReview.review_type)
    ).all()
    by_outcome_rows = db.execute(
        select(AISystemGovernanceReview.outcome, func.count(AISystemGovernanceReview.id))
        .where(
            AISystemGovernanceReview.organization_id == organization.id,
            AISystemGovernanceReview.ai_system_id == ai_system.id,
            AISystemGovernanceReview.outcome.is_not(None),
        )
        .group_by(AISystemGovernanceReview.outcome)
    ).all()
    total_attestations = int(
        db.execute(
            select(func.count(AISystemGovernanceAttestation.id)).where(
                AISystemGovernanceAttestation.organization_id == organization.id,
                AISystemGovernanceAttestation.ai_system_id == ai_system.id,
            )
        ).scalar_one()
    )
    latest_review_at = db.execute(
        select(func.max(AISystemGovernanceReview.created_at)).where(
            AISystemGovernanceReview.organization_id == organization.id,
            AISystemGovernanceReview.ai_system_id == ai_system.id,
        )
    ).scalar_one()
    latest_attestation_at = db.execute(
        select(func.max(AISystemGovernanceAttestation.created_at)).where(
            AISystemGovernanceAttestation.organization_id == organization.id,
            AISystemGovernanceAttestation.ai_system_id == ai_system.id,
        )
    ).scalar_one()
    return AISystemGovernanceSummary(
        total_reviews=total_reviews,
        pending_reviews=pending_reviews,
        in_progress_reviews=in_progress_reviews,
        completed_reviews=completed_reviews,
        cancelled_reviews=cancelled_reviews,
        by_review_type={str(key): int(count) for key, count in by_review_type_rows if key is not None},
        by_outcome={str(key): int(count) for key, count in by_outcome_rows if key is not None},
        total_attestations=total_attestations,
        latest_review_at=latest_review_at,
        latest_attestation_at=latest_attestation_at,
    )


@router.get("/summary", response_model=AISystemSummary)
def ai_system_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemSummary:
    return AISystemSummary(**AISystemService(db).summary(organization.id))


@router.get("", response_model=list[AISystemRead])
def list_ai_systems(
    lifecycle_status: str | None = Query(default=None),
    system_type: str | None = Query(default=None),
    owner_user_id: uuid.UUID | None = Query(default=None),
    include_archived: bool = Query(default=False),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemRead]:
    stmt = select(AISystem).where(AISystem.organization_id == organization.id)

    if lifecycle_status:
        stmt = stmt.where(AISystem.lifecycle_status == lifecycle_status)
    if system_type:
        stmt = stmt.where(AISystem.system_type == system_type)
    if owner_user_id:
        stmt = stmt.where(
            or_(
                AISystem.business_owner_user_id == owner_user_id,
                AISystem.technical_owner_user_id == owner_user_id,
            )
        )
    if not include_archived:
        stmt = stmt.where(AISystem.lifecycle_status != "archived")

    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                AISystem.name.ilike(like),
                AISystem.description.ilike(like),
                AISystem.vendor_name.ilike(like),
                AISystem.provider_name.ilike(like),
                AISystem.model_name.ilike(like),
                AISystem.intended_purpose.ilike(like),
                AISystem.use_case.ilike(like),
            )
        )

    stmt = stmt.order_by(AISystem.created_at.desc()).offset(offset).limit(limit)
    rows = db.execute(stmt).scalars().all()
    return [_ai_system_read(row) for row in rows]


@router.get("/{ai_system_id}", response_model=AISystemRead)
def get_ai_system(
    ai_system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemRead:
    row = AISystemService(db).require_ai_system_in_org(organization.id, ai_system_id)
    return _ai_system_read(row)


@router.patch("/{ai_system_id}", response_model=AISystemRead)
def update_ai_system(
    ai_system_id: uuid.UUID,
    payload: AISystemUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRead:
    service = AISystemService(db)
    row = service.require_ai_system_in_org(organization.id, ai_system_id)
    changes = payload.model_dump(exclude_unset=True)

    if row.lifecycle_status == "archived":
        disallowed = sorted([field for field in changes if field not in {"notes", "tags_json"}])
        if disallowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Archived AI systems can only update notes and tags_json",
            )

    if "business_owner_user_id" in changes:
        service.ensure_owner_is_active_member(
            organization.id,
            changes["business_owner_user_id"],
            field_name="business_owner_user_id",
        )
    if "technical_owner_user_id" in changes:
        service.ensure_owner_is_active_member(
            organization.id,
            changes["technical_owner_user_id"],
            field_name="technical_owner_user_id",
        )

    before = {
        "name": row.name,
        "system_type": row.system_type,
        "lifecycle_status": row.lifecycle_status,
        "business_owner_user_id": str(row.business_owner_user_id) if row.business_owner_user_id else None,
        "technical_owner_user_id": str(row.technical_owner_user_id) if row.technical_owner_user_id else None,
        "archived_at": row.archived_at.isoformat() if row.archived_at else None,
    }

    for field, value in changes.items():
        setattr(row, field, value)
    row.updated_by_user_id = current_user.id
    db.flush()

    AuditService(db).write_audit_log(
        action="ai_system.updated",
        entity_type="ai_system",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "name": row.name,
            "system_type": row.system_type,
            "lifecycle_status": row.lifecycle_status,
            "business_owner_user_id": str(row.business_owner_user_id) if row.business_owner_user_id else None,
            "technical_owner_user_id": str(row.technical_owner_user_id) if row.technical_owner_user_id else None,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _ai_system_read(row)


@router.post("/{ai_system_id}/archive", response_model=AISystemRead)
def archive_ai_system(
    ai_system_id: uuid.UUID,
    payload: AISystemArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:admin")),
) -> AISystemRead:
    row = AISystemService(db).require_ai_system_in_org(organization.id, ai_system_id)
    before = {
        "lifecycle_status": row.lifecycle_status,
        "archived_at": row.archived_at.isoformat() if row.archived_at else None,
        "archived_by_user_id": str(row.archived_by_user_id) if row.archived_by_user_id else None,
    }

    row.lifecycle_status = "archived"
    if row.archived_at is None:
        row.archived_at = datetime.now(UTC)
    row.archived_by_user_id = current_user.id
    row.updated_by_user_id = current_user.id
    db.flush()

    AuditService(db).write_audit_log(
        action="ai_system.archived",
        entity_type="ai_system",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "lifecycle_status": row.lifecycle_status,
            "archived_at": row.archived_at.isoformat() if row.archived_at else None,
            "archived_by_user_id": str(row.archived_by_user_id) if row.archived_by_user_id else None,
        },
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _ai_system_read(row)
