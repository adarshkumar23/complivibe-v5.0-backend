import hashlib
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.billing_deps import require_capacity
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
    EvidenceAiAssessmentRead,
    EvidenceFileUploadResponse,
    EvidenceFileUrlResponse,
    EvidenceRead,
    EvidenceReadinessSummary,
    EvidenceReviewRequest,
    EvidenceUpdate,
)
from app.compliance.services.webhook_service import WebhookService
from app.services.audit_service import AuditService
from app.services.evidence_service import EvidenceService
from app.services.object_storage_service import (
    PROVIDER_NAME as R2_PROVIDER_NAME,
    ObjectStorageService,
    StorageNotConfiguredError,
)

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
        webhook_service = WebhookService(db)
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
            webhook_service.emit(
                organization.id,
                "evidence.expired",
                {
                    "evidence_id": str(row.id),
                    "title": row.title,
                    "evidence_type": row.evidence_type,
                    "valid_until": row.valid_until.isoformat() if row.valid_until else None,
                },
            )
        # The db.commit() above ran before the webhook deliveries were queued;
        # commit again so they're actually persisted instead of left pending in
        # the session.
        db.commit()
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
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("evidence:write")),
    __: Organization = require_capacity("evidence"),
) -> EvidenceRead:
    # Routed through EvidenceService.create_evidence_item so the manual upload path
    # shares the same checksum-based dedup as the webhook/email/form automation paths
    # (see app/services/evidence_automation_service.py) instead of re-implementing
    # evidence-row creation (and silently skipping dedup) here.
    evidence, _, is_duplicate = EvidenceService(db).create_evidence_item(
        organization_id=organization.id,
        actor_user_id=current_user.id,
        title=payload.title,
        description=payload.description,
        evidence_type=payload.evidence_type,
        source=payload.source,
        file_name=payload.file_name,
        mime_type=payload.mime_type,
        size_bytes=payload.size_bytes,
        checksum_sha256=payload.checksum_sha256,
        external_reference_url=payload.external_reference_url,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
        collected_at=payload.collected_at,
        metadata_json=payload.metadata_json,
        request_ip=request.client.host if request.client else None,
        request_user_agent=request.headers.get("user-agent"),
        audit_metadata={"source": "api"},
    )

    db.commit()
    db.refresh(evidence)

    if is_duplicate:
        # A checksum match against an existing, active evidence item was found: no new
        # row was created. Signal this to the caller via status code + header rather
        # than silently returning 201 as if a fresh evidence item had been created.
        response.status_code = status.HTTP_200_OK
        response.headers["X-Evidence-Duplicate-Of"] = str(evidence.id)

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
        WebhookService(db).emit(
            organization.id,
            "evidence.expired",
            {
                "evidence_id": str(evidence.id),
                "title": evidence.title,
                "evidence_type": evidence.evidence_type,
                "valid_until": evidence.valid_until.isoformat() if evidence.valid_until else None,
            },
        )
        # The db.commit() above ran before the webhook delivery was queued; commit
        # again so it's actually persisted instead of left pending in the session.
        db.commit()
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
        # No file_name / mime_type / size_bytes / checksum_sha256: these describe the stored
        # bytes, are computed server-side at upload, and must not be rewritable afterwards.
        # See EvidenceUpdate.
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


# ── Evidence file storage (Cloudflare R2) ───────────────────────────────────
# Extension allowlist (secure by default): documents + images only. Anything not
# listed -- executables, scripts, archives-of-code -- is rejected. The extension
# is the primary gate because the multipart content-type is client-declared and
# spoofable; we still record a normalized content-type for correct download
# rendering. NOTE: this is allowlist validation only -- there is NO malware/virus
# scanning and NO deep content-sniffing in this build (documented known gap).
_ALLOWED_EXTENSIONS: dict[str, str] = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".json": "application/json",
    ".xml": "application/xml",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def _validate_and_normalize_upload(filename: str | None) -> tuple[str, str]:
    """Return (sanitized_extension, normalized_content_type) or raise 415."""
    from pathlib import PurePosixPath

    if not filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A filename is required for file upload.")
    ext = PurePosixPath(filename).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"File type '{ext or '(none)'}' is not allowed. Permitted evidence file "
                f"types: {', '.join(sorted(_ALLOWED_EXTENSIONS))}."
            ),
        )
    return ext, _ALLOWED_EXTENSIONS[ext]


async def _read_bounded(upload: UploadFile, max_bytes: int) -> bytes:
    """Read the upload, enforcing the size cap incrementally (reject before OOM)."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds the maximum evidence upload size of {max_bytes} bytes.",
            )
        chunks.append(chunk)
    if total == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")
    return b"".join(chunks)


@router.post("/{evidence_id}/file", response_model=EvidenceFileUploadResponse)
async def upload_evidence_file(
    evidence_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("evidence:write")),
) -> EvidenceFileUploadResponse:
    """Attach a real file to an existing evidence item, stored in Cloudflare R2.

    Complements (does not replace) the metadata/external_reference_url path: an
    evidence item can carry either an uploaded file, an external link, or both.
    Gracefully inert -- if R2 is not configured this returns 503 without touching
    the row, so the metadata path keeps working.
    """
    from app.core.config import get_settings

    evidence = _get_evidence_or_404(db, organization.id, evidence_id)

    storage = ObjectStorageService()
    if not storage.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Object storage (Cloudflare R2) is not configured; file upload is unavailable. "
            "Evidence can still be recorded via metadata and an external_reference_url.",
        )

    ext, content_type = _validate_and_normalize_upload(file.filename)
    data = await _read_bounded(file, get_settings().EVIDENCE_MAX_UPLOAD_BYTES)

    # SHA-256 computed from the ACTUAL bytes -- replaces the previously
    # client-supplied, unverified checksum for file-backed evidence.
    checksum = hashlib.sha256(data).hexdigest()
    key = ObjectStorageService.build_key(organization.id, evidence.id, file.filename)

    try:
        storage.upload_bytes(key, data, content_type)
    except StorageNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 -- surface storage failures, never a 500 stacktrace
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to store the file in object storage: {exc}",
        ) from exc

    evidence.storage_provider = R2_PROVIDER_NAME
    evidence.storage_key = key
    evidence.file_name = file.filename[:255]
    evidence.mime_type = content_type
    evidence.size_bytes = len(data)
    evidence.checksum_sha256 = checksum
    db.flush()

    AuditService(db).write_audit_log(
        organization_id=organization.id,
        actor_user_id=current_user.id,
        action="evidence.file_uploaded",
        entity_type="evidence_item",
        entity_id=evidence.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata_json={"storage_provider": R2_PROVIDER_NAME, "size_bytes": len(data), "checksum_sha256": checksum},
    )
    db.commit()
    db.refresh(evidence)

    # Fire the EVIDENCE_UPLOADED domain event (previously missing) so downstream
    # async consumers (e.g. the planned AI-assist) can react without blocking upload.
    EventBus.get_instance().emit(
        EventType.EVIDENCE_UPLOADED,
        EventPayload(
            org_id=organization.id,
            entity_type="evidence",
            entity_id=evidence.id,
            event_type=EventType.EVIDENCE_UPLOADED,
            previous_value=None,
            new_value=key,
            triggered_by="user",
            triggered_by_user_id=current_user.id,
            db=db,
        ),
    )
    db.commit()

    return EvidenceFileUploadResponse(
        evidence_id=evidence.id,
        storage_provider=R2_PROVIDER_NAME,
        storage_key=key,
        file_name=evidence.file_name,
        mime_type=content_type,
        size_bytes=len(data),
        checksum_sha256=checksum,
    )


@router.get("/{evidence_id}/file-url", response_model=EvidenceFileUrlResponse)
def get_evidence_file_url(
    evidence_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("evidence:read")),
) -> EvidenceFileUrlResponse:
    """Return a short-lived presigned GET URL for an evidence item's stored file.

    Org-scoped: _get_evidence_or_404 rejects any evidence_id not owned by the
    caller's organization, so org A cannot mint a URL for org B's file. The object
    key is read from the row (server-derived), never from client input.
    """
    from app.core.config import get_settings

    evidence = _get_evidence_or_404(db, organization.id, evidence_id)
    if not evidence.storage_key or evidence.storage_provider != R2_PROVIDER_NAME:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This evidence item has no stored file. It may only carry an external_reference_url.",
        )

    storage = ObjectStorageService()
    if not storage.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Object storage (Cloudflare R2) is not configured; cannot generate a download URL.",
        )
    try:
        url = storage.generate_presigned_get_url(evidence.storage_key)
    except StorageNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return EvidenceFileUrlResponse(
        evidence_id=evidence.id,
        url=url,
        expires_in_seconds=get_settings().R2_SIGNED_URL_TTL_SECONDS,
    )


@router.get("/{evidence_id}/ai-assessment", response_model=EvidenceAiAssessmentRead)
def get_evidence_ai_assessment(
    evidence_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("evidence:read")),
) -> EvidenceAiAssessmentRead:
    """Return the latest AI ASSESSMENT (a suggestion with reasoning, never a
    verdict) for an evidence item.

    Reuses evidence:read: the assessment is a read-only sub-resource of the
    evidence item at the same sensitivity tier, so anyone who may read the
    evidence may read its assessment -- avoiding RBAC scope-creep and a role-grant
    migration. Org-scoped via _get_evidence_or_404, so org A cannot read org B's
    assessment. Returns 404 while the async assessment is still pending.
    """
    from app.models.evidence_ai_assessment import EvidenceAiAssessment

    evidence = _get_evidence_or_404(db, organization.id, evidence_id)
    assessment = db.execute(
        select(EvidenceAiAssessment)
        .where(
            EvidenceAiAssessment.evidence_item_id == evidence.id,
            EvidenceAiAssessment.organization_id == organization.id,
        )
        .order_by(EvidenceAiAssessment.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No AI assessment is available yet for this evidence item (it may still be processing).",
        )
    return EvidenceAiAssessmentRead(
        evidence_id=evidence.id,
        ai_assessment_status=assessment.ai_assessment_status,
        appears_to_be=assessment.appears_to_be,
        appears_to_cover=assessment.appears_to_cover,
        missing_or_mismatched=list(assessment.missing_or_mismatched_json or []),
        explanation=assessment.explanation,
        linked_control_id=assessment.linked_control_id,
        content_source=assessment.content_source,
        provider_used=assessment.provider_used,
        assessment_version=assessment.assessment_version,
        created_at=assessment.created_at,
    )
