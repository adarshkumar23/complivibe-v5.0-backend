import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.core.event_bus import EventBus, EventPayload, EventType
from app.models.control import Control
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.repositories.evidence_control_link_repository import EvidenceControlLinkRepository
from app.repositories.evidence_repository import EvidenceRepository
from app.schemas.evidence import (
    EvidenceControlGapPage,
    EvidenceControlLinkCreate,
    EvidenceControlLinkRead,
    EvidenceControlSummary,
    EvidenceCreate,
    EvidenceDetail,
    EvidenceRead,
    EvidenceReadinessSummary,
    EvidenceReviewRequest,
    EvidenceUpdate,
)
from app.services.audit_service import AuditService
from app.services.evidence_service import EvidenceService

router = APIRouter(prefix="/evidence", tags=["evidence"])


def _evidence_read(item: EvidenceItem) -> EvidenceRead:
    return EvidenceRead(
        id=item.id,
        organization_id=item.organization_id,
        title=item.title,
        description=item.description,
        evidence_type=item.evidence_type,
        source=item.source,
        status=item.status,
        review_status=item.review_status,
        freshness_status=item.freshness_status,
        file_name=item.file_name,
        mime_type=item.mime_type,
        size_bytes=item.size_bytes,
        checksum_sha256=item.checksum_sha256,
        storage_provider=item.storage_provider,
        storage_key=item.storage_key,
        external_reference_url=item.external_reference_url,
        valid_from=item.valid_from,
        valid_until=item.valid_until,
        collected_at=item.collected_at,
        original_created_at=item.original_created_at,
        uploaded_by_user_id=item.uploaded_by_user_id,
        reviewed_by_user_id=item.reviewed_by_user_id,
        reviewed_at=item.reviewed_at,
        review_notes=item.review_notes,
        metadata_json=item.metadata_json,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _link_read(link: EvidenceControlLink) -> EvidenceControlLinkRead:
    return EvidenceControlLinkRead(
        id=link.id,
        organization_id=link.organization_id,
        evidence_item_id=link.evidence_item_id,
        control_id=link.control_id,
        link_status=link.link_status,
        confidence=link.confidence,
        rationale=link.rationale,
        linked_by_user_id=link.linked_by_user_id,
        linked_at=link.linked_at,
        unlinked_at=link.unlinked_at,
        created_at=link.created_at,
        updated_at=link.updated_at,
    )


def _get_evidence_or_404(db: Session, organization_id: uuid.UUID, evidence_id: uuid.UUID) -> EvidenceItem:
    evidence = EvidenceRepository(db).get_by_id(evidence_id)
    if evidence is None or evidence.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")
    return evidence


def _is_expired(item: EvidenceItem, now: datetime) -> bool:
    if item.valid_until is None or item.freshness_status == "expired":
        return False
    valid_until = item.valid_until
    compare_now = now
    if valid_until.tzinfo is None:
        compare_now = now.replace(tzinfo=None)
    return valid_until < compare_now


@router.get("", response_model=list[EvidenceRead])
def list_evidence(
    review_status: str | None = Query(default=None),
    freshness_status: str | None = Query(default=None),
    evidence_type: str | None = Query(default=None),
    source: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("evidence:read")),
    ) -> list[EvidenceRead]:
    rows = EvidenceRepository(db).list_by_organization(
        organization.id,
        review_status=review_status,
        freshness_status=freshness_status,
        evidence_type=evidence_type,
        source=source,
        search=search,
        limit=limit,
        offset=offset,
    )
    now = datetime.now(UTC)
    expired_rows = [row for row in rows if _is_expired(row, now) and row.status != "archived"]
    if expired_rows:
        for row in expired_rows:
            row.freshness_status = "expired"
        db.flush()
        db.commit()
        bus = EventBus.get_instance()
        for row in expired_rows:
            bus.emit(
                EventType.EVIDENCE_EXPIRED,
                EventPayload(
                    org_id=organization.id,
                    entity_type="evidence",
                    entity_id=row.id,
                    event_type=EventType.EVIDENCE_EXPIRED,
                    previous_value="active",
                    new_value="expired",
                    triggered_by="system",
                    db=db,
                ),
            )
    return [_evidence_read(row) for row in rows]


@router.get("/readiness/summary", response_model=EvidenceReadinessSummary)
def readiness_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("evidence:read")),
) -> EvidenceReadinessSummary:
    return EvidenceReadinessSummary(**EvidenceService(db).readiness_summary(organization.id))


@router.get("/readiness/gaps", response_model=EvidenceControlGapPage)
def readiness_gaps(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("evidence:read")),
) -> EvidenceControlGapPage:
    return EvidenceControlGapPage(**EvidenceService(db).list_control_gaps(organization.id, limit=limit, offset=offset))


@router.post("", response_model=EvidenceRead, status_code=status.HTTP_201_CREATED)
def create_evidence(
    payload: EvidenceCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("evidence:write")),
) -> EvidenceRead:
    if payload.valid_from and payload.valid_until and payload.valid_until < payload.valid_from:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="valid_until cannot be earlier than valid_from")

    freshness = EvidenceService.calculate_freshness_status(payload.valid_until)
    evidence = EvidenceItem(
        organization_id=organization.id,
        title=payload.title,
        description=payload.description,
        evidence_type=payload.evidence_type,
        source=payload.source,
        status="active",
        review_status="not_reviewed",
        freshness_status=freshness,
        file_name=payload.file_name,
        mime_type=payload.mime_type,
        size_bytes=payload.size_bytes,
        checksum_sha256=payload.checksum_sha256,
        external_reference_url=payload.external_reference_url,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
        collected_at=payload.collected_at,
        uploaded_by_user_id=current_user.id,
        metadata_json=payload.metadata_json,
    )
    db.add(evidence)
    db.flush()

    AuditService(db).write_audit_log(
        action="evidence.created",
        entity_type="evidence_item",
        entity_id=evidence.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "title": evidence.title,
            "status": evidence.status,
            "review_status": evidence.review_status,
            "freshness_status": evidence.freshness_status,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(evidence)
    return _evidence_read(evidence)


@router.get("/{evidence_id}", response_model=EvidenceDetail)
def get_evidence_detail(
    evidence_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("evidence:read")),
) -> EvidenceDetail:
    evidence = _get_evidence_or_404(db, organization.id, evidence_id)
    now = datetime.now(UTC)
    if _is_expired(evidence, now) and evidence.status != "archived":
        evidence.freshness_status = "expired"
        db.flush()
        db.commit()
        EventBus.get_instance().emit(
            EventType.EVIDENCE_EXPIRED,
            EventPayload(
                org_id=organization.id,
                entity_type="evidence",
                entity_id=evidence.id,
                event_type=EventType.EVIDENCE_EXPIRED,
                previous_value="active",
                new_value="expired",
                triggered_by="system",
                db=db,
            ),
        )
    links = EvidenceControlLinkRepository(db).list_for_evidence(organization.id, evidence.id)

    control_ids = [l.control_id for l in links]
    controls: list[Control] = []
    if control_ids:
        controls = db.execute(
            select(Control).where(
                Control.organization_id == organization.id,
                Control.id.in_(control_ids),
            )
        ).scalars().all()

    control_map = {c.id: c for c in controls}
    linked_controls = [
        EvidenceControlSummary(control_id=c.id, title=c.title, status=c.status)
        for link in links
        if (c := control_map.get(link.control_id)) is not None
    ]
    return EvidenceDetail(**_evidence_read(evidence).model_dump(), linked_controls=linked_controls)


@router.patch("/{evidence_id}", response_model=EvidenceRead)
def update_evidence(
    evidence_id: uuid.UUID,
    payload: EvidenceUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("evidence:write")),
) -> EvidenceRead:
    evidence = _get_evidence_or_404(db, organization.id, evidence_id)

    if payload.valid_from and payload.valid_until and payload.valid_until < payload.valid_from:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="valid_until cannot be earlier than valid_from")

    before = {
        "title": evidence.title,
        "description": evidence.description,
        "status": evidence.status,
        "review_status": evidence.review_status,
        "freshness_status": evidence.freshness_status,
        "valid_from": evidence.valid_from.isoformat() if evidence.valid_from else None,
        "valid_until": evidence.valid_until.isoformat() if evidence.valid_until else None,
    }

    for field in [
        "title",
        "description",
        "evidence_type",
        "source",
        "status",
        "file_name",
        "mime_type",
        "size_bytes",
        "checksum_sha256",
        "external_reference_url",
        "valid_from",
        "valid_until",
        "collected_at",
        "metadata_json",
    ]:
        value = getattr(payload, field)
        if value is not None:
            setattr(evidence, field, value)

    evidence.freshness_status = EvidenceService.calculate_freshness_status(evidence.valid_until)
    db.flush()

    AuditService(db).write_audit_log(
        action="evidence.updated",
        entity_type="evidence_item",
        entity_id=evidence.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "title": evidence.title,
            "status": evidence.status,
            "review_status": evidence.review_status,
            "freshness_status": evidence.freshness_status,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(evidence)
    return _evidence_read(evidence)


@router.patch("/{evidence_id}/archive", response_model=EvidenceRead)
def archive_evidence(
    evidence_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("evidence:write")),
) -> EvidenceRead:
    evidence = _get_evidence_or_404(db, organization.id, evidence_id)
    before_status = evidence.status
    evidence.status = "archived"
    db.flush()

    AuditService(db).write_audit_log(
        action="evidence.archived",
        entity_type="evidence_item",
        entity_id=evidence.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json={"status": before_status},
        after_json={"status": evidence.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(evidence)
    return _evidence_read(evidence)


@router.post("/{evidence_id}/controls", response_model=EvidenceControlLinkRead)
def link_evidence_to_control(
    evidence_id: uuid.UUID,
    payload: EvidenceControlLinkCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("evidence:write")),
) -> EvidenceControlLinkRead:
    evidence = _get_evidence_or_404(db, organization.id, evidence_id)
    EvidenceService(db).require_control_in_org(organization.id, payload.control_id)

    repo = EvidenceControlLinkRepository(db)
    link = repo.get(organization.id, evidence.id, payload.control_id)
    now = datetime.now(UTC)
    if link is None:
        link = EvidenceControlLink(
            organization_id=organization.id,
            evidence_item_id=evidence.id,
            control_id=payload.control_id,
            link_status="active",
            confidence=payload.confidence,
            rationale=payload.rationale,
            linked_by_user_id=current_user.id,
            linked_at=now,
        )
        db.add(link)
    elif link.link_status != "active":
        link.link_status = "active"
        link.confidence = payload.confidence
        link.rationale = payload.rationale
        link.linked_by_user_id = current_user.id
        link.linked_at = now
        link.unlinked_at = None

    db.flush()

    AuditService(db).write_audit_log(
        action="evidence.control_linked",
        entity_type="evidence_control_link",
        entity_id=link.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "evidence_item_id": str(evidence.id),
            "control_id": str(payload.control_id),
            "link_status": link.link_status,
            "confidence": link.confidence,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(link)
    return _link_read(link)


@router.delete("/{evidence_id}/controls/{control_id}", response_model=EvidenceControlLinkRead)
def unlink_evidence_from_control(
    evidence_id: uuid.UUID,
    control_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("evidence:write")),
) -> EvidenceControlLinkRead:
    evidence = _get_evidence_or_404(db, organization.id, evidence_id)
    link = EvidenceControlLinkRepository(db).get(organization.id, evidence.id, control_id)
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence-control link not found")

    before = {"link_status": link.link_status}
    link.link_status = "inactive"
    link.unlinked_at = datetime.now(UTC)
    db.flush()

    AuditService(db).write_audit_log(
        action="evidence.control_unlinked",
        entity_type="evidence_control_link",
        entity_id=link.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"link_status": link.link_status},
        metadata_json={"source": "api", "control_id": str(control_id)},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(link)
    return _link_read(link)


@router.post("/{evidence_id}/review", response_model=EvidenceRead)
def review_evidence(
    evidence_id: uuid.UUID,
    payload: EvidenceReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("evidence:write")),
) -> EvidenceRead:
    evidence = _get_evidence_or_404(db, organization.id, evidence_id)
    if payload.review_status == "rejected" and not (payload.review_notes and payload.review_notes.strip()):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="review_notes is required when review_status is rejected")

    service = EvidenceService(db)
    evidence, before_status = service.set_review_status_and_emit(
        organization.id,
        evidence.id,
        review_status=payload.review_status,
        review_notes=payload.review_notes,
        reviewed_by_user_id=current_user.id,
        triggered_by="user_action",
    )

    AuditService(db).write_audit_log(
        action="evidence.reviewed",
        entity_type="evidence_item",
        entity_id=evidence.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json={"review_status": before_status},
        after_json={"review_status": evidence.review_status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(evidence)
    return _evidence_read(evidence)
