import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.control import Control
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.evidence_item import EvidenceItem
from app.models.membership import Membership
from app.models.obligation import Obligation
from app.models.organization import Organization
from app.models.user import User
from app.repositories.control_mapping_repository import ControlMappingRepository
from app.repositories.control_repository import ControlRepository
from app.repositories.evidence_control_link_repository import EvidenceControlLinkRepository
from app.schemas.control import (
    ControlCreate,
    ControlDetail,
    ControlGapSummary,
    ControlObligationMapCreate,
    ControlObligationMapRead,
    ControlRead,
    ControlUpdate,
)
from app.schemas.common_controls import CommonControlCoverageReport
from app.schemas.evidence import EvidenceRead
from app.api.v1.evidence import _evidence_read
from app.compliance.services.common_controls_service import CommonControlsService
from app.compliance.services.control_exception_service import ControlExceptionService
from app.services.audit_service import AuditService
from app.services.control_service import ControlService
from app.compliance.services.issue_control_link_service import IssueControlLinkService
from app.schemas.issue_links import ControlAssociatedIssuesGroupedRead, ControlFailureRateRead

router = APIRouter(prefix="/controls", tags=["controls"])


def _control_read(control: Control, *, owner_membership_active: bool | None = None) -> ControlRead:
    return ControlRead(
        id=control.id,
        organization_id=control.organization_id,
        title=control.title,
        description=control.description,
        control_code=control.control_code,
        control_type=control.control_type,
        status=control.status,
        criticality=control.criticality,
        owner_user_id=control.owner_user_id,
        last_reviewed_at=control.last_reviewed_at,
        testing_procedure=control.testing_procedure,
        implementation_notes=control.implementation_notes,
        source=control.source,
        created_by_user_id=control.created_by_user_id,
        created_at=control.created_at,
        updated_at=control.updated_at,
        owner_membership_active=owner_membership_active,
    )


def _get_control_or_404(db: Session, organization_id: uuid.UUID, control_id: uuid.UUID) -> Control:
    control = ControlRepository(db).get_by_id(control_id)
    if control is None or control.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control not found")
    return control


def _active_owner_ids(db: Session, organization_id: uuid.UUID, owner_ids: set[uuid.UUID]) -> set[uuid.UUID]:
    """Batch-resolve which of the given user ids currently hold an active membership in the
    org, in a single query -- so listing N controls doesn't cost N membership lookups."""
    if not owner_ids:
        return set()
    rows = db.execute(
        select(Membership.user_id).where(
            Membership.organization_id == organization_id,
            Membership.user_id.in_(owner_ids),
            Membership.status == "active",
        )
    ).scalars().all()
    return set(rows)


def _control_read_with_owner_status(db: Session, organization_id: uuid.UUID, control: Control) -> ControlRead:
    owner_membership_active = None
    if control.owner_user_id is not None:
        owner_membership_active = control.owner_user_id in _active_owner_ids(db, organization_id, {control.owner_user_id})
    return _control_read(control, owner_membership_active=owner_membership_active)


@router.get("/gaps/summary", response_model=ControlGapSummary)
def control_gap_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:read")),
) -> ControlGapSummary:
    return ControlGapSummary(**ControlService.gap_summary(db, organization.id))


@router.get("", response_model=list[ControlRead])
def list_controls(
    status: str | None = Query(default=None),
    criticality: str | None = Query(default=None),
    owner_user_id: uuid.UUID | None = Query(default=None),
    business_unit_id: uuid.UUID | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:read")),
) -> list[ControlRead]:
    controls = ControlRepository(db).list_by_organization(
        organization.id,
        status=status,
        criticality=criticality,
        owner_user_id=owner_user_id,
        business_unit_id=business_unit_id,
        search=search,
        limit=limit,
        offset=offset,
    )
    owner_ids = {c.owner_user_id for c in controls if c.owner_user_id is not None}
    active_owner_ids = _active_owner_ids(db, organization.id, owner_ids)
    return [
        _control_read(
            c,
            owner_membership_active=(c.owner_user_id in active_owner_ids) if c.owner_user_id is not None else None,
        )
        for c in controls
    ]


@router.post("", response_model=ControlRead, status_code=status.HTTP_201_CREATED)
def create_control(
    payload: ControlCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:write")),
) -> ControlRead:
    ControlService.ensure_owner_is_active_member(db, organization.id, payload.owner_user_id)

    control = Control(
        organization_id=organization.id,
        title=payload.title,
        description=payload.description,
        control_code=payload.control_code,
        control_type=payload.control_type,
        status="not_started",
        criticality=payload.criticality,
        owner_user_id=payload.owner_user_id,
        testing_procedure=payload.testing_procedure,
        implementation_notes=payload.implementation_notes,
        source="custom",
        created_by_user_id=current_user.id,
    )
    db.add(control)
    db.flush()

    AuditService(db).write_audit_log(
        action="control.created",
        entity_type="control",
        entity_id=control.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"title": control.title, "status": control.status, "criticality": control.criticality},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(control)
    return _control_read_with_owner_status(db, organization.id, control)


@router.get("/{control_id}", response_model=ControlDetail)
def get_control_detail(
    control_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:read")),
) -> ControlDetail:
    control = _get_control_or_404(db, organization.id, control_id)

    mappings = ControlMappingRepository(db).list_for_control(organization.id, control.id)
    mapped_summary = [
        ControlObligationMapRead(
            obligation_id=m.obligation_id,
            mapping_type=m.mapping_type,
            confidence=m.confidence,
            status=m.status,
        )
        for m in mappings
    ]

    evidence_count = ControlService.evidence_count_for_control(db, organization.id, control.id)
    active_exception = ControlExceptionService(db).get_control_exception_status(control.id, organization.id)
    exception_context = (
        {
            "id": str(active_exception.id),
            "title": active_exception.title,
            "status": active_exception.status,
            "exception_type": active_exception.exception_type,
            "risk_acceptance_reason": active_exception.risk_acceptance_reason,
            "effective_date": str(active_exception.effective_date),
            "expiry_date": str(active_exception.expiry_date) if active_exception.expiry_date else None,
            "review_date": str(active_exception.review_date) if active_exception.review_date else None,
            "review_overdue": (
                active_exception.review_date is not None
                and active_exception.review_date < ControlExceptionService.utcdate()
            ),
        }
        if active_exception is not None
        else None
    )
    return ControlDetail(
        **_control_read_with_owner_status(db, organization.id, control).model_dump(),
        mapped_obligations=mapped_summary,
        evidence_count=evidence_count,
        active_exception=exception_context,
    )


@router.get("/{control_id}/associated-issues", response_model=ControlAssociatedIssuesGroupedRead)
def get_control_associated_issues(
    control_id: uuid.UUID,
    failure_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:read")),
) -> ControlAssociatedIssuesGroupedRead:
    payload = IssueControlLinkService(db).get_control_associated_issues(
        organization.id,
        control_id,
        failure_type=failure_type,
        status_value=status_filter,
    )
    return ControlAssociatedIssuesGroupedRead(**payload)


@router.get("/{control_id}/failure-rate", response_model=ControlFailureRateRead)
def get_control_failure_rate(
    control_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("issues:read")),
) -> ControlFailureRateRead:
    payload = IssueControlLinkService(db).get_control_failure_rate(organization.id, control_id)
    return ControlFailureRateRead(**payload)


@router.get("/{control_id}/framework-coverage", response_model=CommonControlCoverageReport)
def get_control_framework_coverage(
    control_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:read")),
) -> CommonControlCoverageReport:
    payload = CommonControlsService(db).get_coverage_report(control_id, organization.id)
    return CommonControlCoverageReport(**payload)


@router.get("/{control_id}/evidence", response_model=list[EvidenceRead])
def list_evidence_for_control(
    control_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("evidence:read")),
) -> list[EvidenceRead]:
    control = _get_control_or_404(db, organization.id, control_id)

    links = EvidenceControlLinkRepository(db).list_for_control(organization.id, control.id)
    evidence_ids = [link.evidence_item_id for link in links]
    if not evidence_ids:
        return []

    evidence_rows = db.execute(
        select(EvidenceItem).where(
            EvidenceItem.organization_id == organization.id,
            EvidenceItem.id.in_(evidence_ids),
            EvidenceItem.status != "archived",
        )
    ).scalars().all()
    return [_evidence_read(item) for item in evidence_rows]


@router.patch("/{control_id}", response_model=ControlRead)
def update_control(
    control_id: uuid.UUID,
    payload: ControlUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:write")),
) -> ControlRead:
    control = _get_control_or_404(db, organization.id, control_id)

    if payload.owner_user_id is not None:
        ControlService.ensure_owner_is_active_member(db, organization.id, payload.owner_user_id)

    if payload.status is not None:
        ControlService.validate_status_transition(control.status, payload.status)

    before = {
        "title": control.title,
        "description": control.description,
        "status": control.status,
        "criticality": control.criticality,
        "owner_user_id": str(control.owner_user_id) if control.owner_user_id else None,
        "testing_procedure": control.testing_procedure,
        "implementation_notes": control.implementation_notes,
    }

    for field in ["title", "description", "status", "criticality", "owner_user_id", "testing_procedure", "implementation_notes"]:
        value = getattr(payload, field)
        if value is not None:
            setattr(control, field, value)

    db.flush()

    after = {
        "title": control.title,
        "description": control.description,
        "status": control.status,
        "criticality": control.criticality,
        "owner_user_id": str(control.owner_user_id) if control.owner_user_id else None,
        "testing_procedure": control.testing_procedure,
        "implementation_notes": control.implementation_notes,
    }

    AuditService(db).write_audit_log(
        action="control.updated",
        entity_type="control",
        entity_id=control.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json=after,
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    ControlService.emit_control_status_changed(
        db,
        organization_id=organization.id,
        control_id=control.id,
        previous_status=before["status"],
        new_status=control.status,
        triggered_by="user_action",
    )
    # emit_control_status_changed may have queued webhook deliveries (e.g. for a
    # transition into "failed"); the commit above ran before that call, so commit
    # again to persist them instead of leaving them stranded in the session.
    db.commit()
    db.refresh(control)
    return _control_read_with_owner_status(db, organization.id, control)


@router.patch("/{control_id}/archive", response_model=ControlRead)
def archive_control(
    control_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:write")),
) -> ControlRead:
    control = _get_control_or_404(db, organization.id, control_id)
    before_status = control.status
    control.status = "archived"
    db.flush()

    AuditService(db).write_audit_log(
        action="control.archived",
        entity_type="control",
        entity_id=control.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json={"status": before_status},
        after_json={"status": control.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    ControlService.emit_control_status_changed(
        db,
        organization_id=organization.id,
        control_id=control.id,
        previous_status=before_status,
        new_status=control.status,
        triggered_by="user_action",
    )
    db.refresh(control)
    return _control_read_with_owner_status(db, organization.id, control)


@router.post("/{control_id}/obligations", response_model=ControlObligationMapRead)
def map_control_to_obligation(
    control_id: uuid.UUID,
    payload: ControlObligationMapCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:write")),
) -> ControlObligationMapRead:
    control = _get_control_or_404(db, organization.id, control_id)
    ControlService.ensure_obligation_framework_is_active(db, organization.id, payload.obligation_id)

    mapping_repo = ControlMappingRepository(db)
    mapping = mapping_repo.get(organization.id, control.id, payload.obligation_id)
    if mapping is None:
        mapping = ControlObligationMapping(
            organization_id=organization.id,
            control_id=control.id,
            obligation_id=payload.obligation_id,
            mapping_type=payload.mapping_type,
            confidence=payload.confidence,
            rationale=payload.rationale,
            status="active",
            created_by_user_id=current_user.id,
        )
        db.add(mapping)
    elif mapping.status != "active":
        mapping.status = "active"
        mapping.mapping_type = payload.mapping_type
        mapping.confidence = payload.confidence
        mapping.rationale = payload.rationale

    db.flush()

    AuditService(db).write_audit_log(
        action="control.obligation_mapped",
        entity_type="control_obligation_mapping",
        entity_id=mapping.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "control_id": str(control.id),
            "obligation_id": str(mapping.obligation_id),
            "mapping_type": mapping.mapping_type,
            "status": mapping.status,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    return ControlObligationMapRead(
        obligation_id=mapping.obligation_id,
        mapping_type=mapping.mapping_type,
        confidence=mapping.confidence,
        status=mapping.status,
    )


@router.delete("/{control_id}/obligations/{obligation_id}", response_model=ControlObligationMapRead)
def unmap_control_from_obligation(
    control_id: uuid.UUID,
    obligation_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:write")),
) -> ControlObligationMapRead:
    control = _get_control_or_404(db, organization.id, control_id)
    mapping_repo = ControlMappingRepository(db)
    mapping = mapping_repo.get(organization.id, control.id, obligation_id)
    if mapping is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control-obligation mapping not found")

    mapping.status = "inactive"
    db.flush()

    AuditService(db).write_audit_log(
        action="control.obligation_unmapped",
        entity_type="control_obligation_mapping",
        entity_id=mapping.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json={"status": "active"},
        after_json={"status": "inactive", "obligation_id": str(obligation_id)},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    return ControlObligationMapRead(
        obligation_id=mapping.obligation_id,
        mapping_type=mapping.mapping_type,
        confidence=mapping.confidence,
        status=mapping.status,
    )
