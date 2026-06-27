from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.compliance.services.trust_center_service import TrustCenterService
from app.core.deps import get_db
from app.schemas.trust_center import (
    TrustCenterAccessRequestCreate,
    TrustCenterAccessRequestSubmitResponse,
    TrustCenterPublicRead,
)

router = APIRouter(prefix="/trust-center", tags=["trust-center-public"])


@router.get("/{slug}", response_model=TrustCenterPublicRead)
def get_trust_center_public_data(
    slug: str,
    db: Session = Depends(get_db),
) -> TrustCenterPublicRead:
    payload = TrustCenterService(db).get_trust_center_public_data(slug)
    return TrustCenterPublicRead(**payload)


@router.post("/{slug}/request-access", response_model=TrustCenterAccessRequestSubmitResponse, status_code=status.HTTP_201_CREATED)
def submit_trust_center_access_request(
    slug: str,
    payload: TrustCenterAccessRequestCreate,
    db: Session = Depends(get_db),
) -> TrustCenterAccessRequestSubmitResponse:
    service = TrustCenterService(db)
    org = service.get_org_by_slug(slug)
    if org is None:
        # Reuse service-level 404 semantics for public trust center.
        service.get_trust_center_public_data(slug)

    result = service.submit_access_request(org.id, payload)
    db.commit()
    return TrustCenterAccessRequestSubmitResponse(**result)
