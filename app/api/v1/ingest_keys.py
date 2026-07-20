from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.subsystem_ingest_key import (
    SubsystemIngestKeyListResponse,
    SubsystemIngestKeyProvisionRequest,
    SubsystemIngestKeyProvisionResponse,
)
from app.services.subsystem_ingest_key_service import SubsystemIngestKeyService

router = APIRouter(prefix="/integrations/ingest-keys", tags=["ingest-keys"])


@router.post("", response_model=SubsystemIngestKeyProvisionResponse, status_code=status.HTTP_201_CREATED)
def provision_subsystem_ingest_key(
    payload: SubsystemIngestKeyProvisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("org:update")),
) -> SubsystemIngestKeyProvisionResponse:
    """Provision (or rotate) this org's inbound machine-ingest key for one subsystem.

    Each inbound subsystem (lineage, cookies, consent, security, access_monitoring,
    pam) has its OWN key so a key leaked from one cannot authenticate another. The raw
    key is returned once; presenting it as X-CompliVibe-Key authenticates only that
    subsystem's ingest endpoints. Rotating replaces the previous key in place.
    """
    raw_key = SubsystemIngestKeyService(db).provision_key(organization.id, payload.key_type, current_user.id)
    db.commit()
    return SubsystemIngestKeyProvisionResponse(api_key=raw_key, key_type=payload.key_type)


@router.get("", response_model=SubsystemIngestKeyListResponse)
def list_subsystem_ingest_keys(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("org:read")),
) -> SubsystemIngestKeyListResponse:
    """List which subsystems currently have an active ingest key (no secret material)."""
    return SubsystemIngestKeyListResponse(
        provisioned_key_types=SubsystemIngestKeyService(db).list_provisioned_key_types(organization.id)
    )
