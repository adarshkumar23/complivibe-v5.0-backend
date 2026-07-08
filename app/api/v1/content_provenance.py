import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.content_provenance import (
    ContentManifestVerifyRequest,
    ContentProvenanceHistoryResponse,
    ContentProvenanceResponse,
)
from app.services.content_provenance_service import ContentProvenanceService

router = APIRouter(prefix="/content-provenance", tags=["content-provenance"])


@router.post("/verify", response_model=ContentProvenanceResponse, status_code=status.HTTP_200_OK)
def verify_content_manifest(
    payload: ContentManifestVerifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("content_provenance:manage")),
) -> ContentProvenanceResponse:
    record = ContentProvenanceService(db).verify_manifest(
        organization.id,
        payload.content_identifier,
        payload.manifest,
        current_user.id,
        content_sha256=payload.content_sha256,
    )
    return ContentProvenanceResponse.model_validate(record)


@router.get("/history/{content_identifier}", response_model=ContentProvenanceHistoryResponse)
def get_content_provenance_history(
    content_identifier: str,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("content_provenance:manage")),
) -> ContentProvenanceHistoryResponse:
    records, drift = ContentProvenanceService(db).get_history(organization.id, content_identifier)
    return ContentProvenanceHistoryResponse(
        content_identifier=content_identifier,
        records=[ContentProvenanceResponse.model_validate(row) for row in records],
        provenance_drift_detected=drift,
    )


@router.get("/{record_id}", response_model=ContentProvenanceResponse)
def get_content_provenance_record(
    record_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("content_provenance:manage")),
) -> ContentProvenanceResponse:
    record = ContentProvenanceService(db).get_record(organization.id, record_id)
    return ContentProvenanceResponse.model_validate(record)
