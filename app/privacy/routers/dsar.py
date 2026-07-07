import uuid
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.core.rate_limiter import rate_limiter
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.privacy.schemas.dsar import (
    DSRAssignRequest,
    DSRExtensionRequest,
    DSRFulfillmentStepCreate,
    DSRFulfillmentStepRead,
    DSRFulfillmentStepUpdate,
    DSRSummaryRead,
    DSRTransitionRequest,
    DataSubjectRequestCreate,
    DataSubjectRequestRead,
    PublicDSRSubmit,
    PublicDSRSubmitResponse,
)
from app.privacy.services.dsar_service import DSARService

router = APIRouter(prefix="/privacy/dsr", tags=["privacy-dsr"])

# Lightweight in-process rate limit for public intake.
_PUBLIC_LIMIT_WINDOW = timedelta(minutes=1)
_PUBLIC_LIMIT_COUNT = 10
_PUBLIC_INTAKE_HISTORY: defaultdict[str, deque[datetime]] = defaultdict(deque)


def _check_public_rate_limit(client_ip: str) -> None:
    now = datetime.now(UTC)
    bucket = _PUBLIC_INTAKE_HISTORY[client_ip]
    cutoff = now - _PUBLIC_LIMIT_WINDOW
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    if len(bucket) >= _PUBLIC_LIMIT_COUNT:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests")
    bucket.append(now)


def _request_read(service: DSARService, row) -> DataSubjectRequestRead:
    return DataSubjectRequestRead.model_validate(service.request_response_payload(row))


@router.post("/submit", response_model=PublicDSRSubmitResponse, status_code=status.HTTP_201_CREATED)
@rate_limiter.limiter.limit("120/minute")
def submit_public_dsr(
    payload: PublicDSRSubmit,
    request: Request,
    db: Session = Depends(get_db),
) -> PublicDSRSubmitResponse:
    client_ip = request.client.host if request.client else "unknown"
    _check_public_rate_limit(client_ip)
    result = DSARService(db).submit_public_request(payload)
    db.commit()
    return PublicDSRSubmitResponse.model_validate(result)


@router.post("", response_model=DataSubjectRequestRead, status_code=status.HTTP_201_CREATED)
def create_request(
    payload: DataSubjectRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> DataSubjectRequestRead:
    service = DSARService(db)
    row = service.create_request(organization.id, payload, created_by=current_user.id)
    db.commit()
    db.refresh(row)
    return _request_read(service, row)


@router.get("", response_model=list[DataSubjectRequestRead])
def list_requests(
    status_filter: str | None = Query(default=None, alias="status"),
    request_type: str | None = Query(default=None),
    assigned_handler_id: uuid.UUID | None = Query(default=None),
    overdue_only: bool = Query(default=False),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> list[DataSubjectRequestRead]:
    service = DSARService(db)
    rows = service.list_requests(
        organization.id,
        status_filter=status_filter,
        request_type=request_type,
        assigned_handler_id=assigned_handler_id,
        overdue_only=overdue_only,
        skip=skip,
        limit=limit,
    )
    return [DataSubjectRequestRead.model_validate(item) for item in service.request_response_payloads(organization.id, rows)]


@router.get("/summary", response_model=DSRSummaryRead)
def get_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> DSRSummaryRead:
    payload = DSARService(db).get_dsr_summary(organization.id)
    return DSRSummaryRead.model_validate(payload)


@router.get("/overdue", response_model=list[DataSubjectRequestRead])
def get_overdue_requests(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> list[DataSubjectRequestRead]:
    service = DSARService(db)
    rows = service.list_requests(
        organization.id,
        overdue_only=True,
        skip=skip,
        limit=limit,
    )
    return [DataSubjectRequestRead.model_validate(item) for item in service.request_response_payloads(organization.id, rows)]


@router.get("/{request_id}", response_model=DataSubjectRequestRead)
def get_request(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> DataSubjectRequestRead:
    service = DSARService(db)
    row = service.get_request(organization.id, request_id)
    return _request_read(service, row)


@router.post("/{request_id}/assign", response_model=DataSubjectRequestRead)
def assign_handler(
    request_id: uuid.UUID,
    payload: DSRAssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> DataSubjectRequestRead:
    service = DSARService(db)
    row = service.assign_handler(organization.id, request_id, payload.handler_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _request_read(service, row)


@router.post("/{request_id}/verify-identity", response_model=DataSubjectRequestRead)
def verify_identity(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> DataSubjectRequestRead:
    service = DSARService(db)
    row = service.verify_identity(organization.id, request_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _request_read(service, row)


@router.post("/{request_id}/transition", response_model=DataSubjectRequestRead)
def transition_status(
    request_id: uuid.UUID,
    payload: DSRTransitionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> DataSubjectRequestRead:
    service = DSARService(db)
    row = service.transition_status(
        organization.id,
        request_id,
        payload.new_status,
        current_user.id,
        notes=payload.notes,
        refusal_reason=payload.refusal_reason,
    )
    db.commit()
    db.refresh(row)
    return _request_read(service, row)


@router.post("/{request_id}/grant-extension", response_model=DataSubjectRequestRead)
def grant_extension(
    request_id: uuid.UUID,
    payload: DSRExtensionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> DataSubjectRequestRead:
    service = DSARService(db)
    row = service.grant_extension(organization.id, request_id, payload.reason, current_user.id)
    db.commit()
    db.refresh(row)
    return _request_read(service, row)


@router.post("/{request_id}/steps", response_model=DSRFulfillmentStepRead, status_code=status.HTTP_201_CREATED)
def add_step(
    request_id: uuid.UUID,
    payload: DSRFulfillmentStepCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> DSRFulfillmentStepRead:
    row = DSARService(db).add_fulfillment_step(organization.id, request_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return DSRFulfillmentStepRead.model_validate(row)


@router.patch("/{request_id}/steps/{step_id}", response_model=DSRFulfillmentStepRead)
def update_step(
    request_id: uuid.UUID,
    step_id: uuid.UUID,
    payload: DSRFulfillmentStepUpdate,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> DSRFulfillmentStepRead:
    row = DSARService(db).update_fulfillment_step(organization.id, request_id, step_id, payload)
    db.commit()
    db.refresh(row)
    return DSRFulfillmentStepRead.model_validate(row)


@router.post("/{request_id}/steps/{step_id}/complete", response_model=DSRFulfillmentStepRead)
def complete_step(
    request_id: uuid.UUID,
    step_id: uuid.UUID,
    notes: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:write")),
) -> DSRFulfillmentStepRead:
    row = DSARService(db).complete_step(organization.id, request_id, step_id, current_user.id, notes=notes)
    db.commit()
    db.refresh(row)
    return DSRFulfillmentStepRead.model_validate(row)


@router.get("/{request_id}/steps", response_model=list[DSRFulfillmentStepRead])
def list_steps(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> list[DSRFulfillmentStepRead]:
    rows = DSARService(db).list_steps(organization.id, request_id)
    return [DSRFulfillmentStepRead.model_validate(row) for row in rows]
