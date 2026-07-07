from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.attestation_tokens import (
    AttestationTokenCreateRequest,
    AttestationTokenCreateResponse,
    AttestationTokenValidationResponse,
)
from app.services.attestation_token_service import AttestationTokenService

router = APIRouter(prefix="/attestation-tokens", tags=["attestation-tokens"])


@router.post("", response_model=AttestationTokenCreateResponse, status_code=201)
def create_attestation_token(
    payload: AttestationTokenCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("attestations:write")),
) -> AttestationTokenCreateResponse:
    row, plaintext_token = AttestationTokenService(db).create_token(
        organization_id=organization.id,
        purpose=payload.purpose,
        scope_json=payload.scope,
        linked_entity_type=payload.linked_entity_type,
        linked_entity_id=payload.linked_entity_id,
        expires_at=payload.expires_at,
        created_by_user_id=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return AttestationTokenCreateResponse(
        token_id=row.id,
        organization_id=row.organization_id,
        purpose=row.purpose,
        linked_entity_type=row.linked_entity_type,
        linked_entity_id=row.linked_entity_id,
        expires_at=row.expires_at,
        plaintext_token=plaintext_token,
        warning="Token is shown only once. Store it securely.",
    )


@router.get("/{token}", response_model=AttestationTokenValidationResponse)
def validate_attestation_token(
    token: str,
    db: Session = Depends(get_db),
) -> AttestationTokenValidationResponse:
    row = AttestationTokenService(db).validate_token(token)
    db.commit()
    db.refresh(row)
    return AttestationTokenValidationResponse(
        token_id=row.id,
        organization_id=row.organization_id,
        purpose=row.purpose,
        scope=row.scope_json or {},
        linked_entity_type=row.linked_entity_type,
        linked_entity_id=row.linked_entity_id,
        status=row.status,
        expires_at=row.expires_at,
        validation_count=row.validation_count,
        last_validated_at=row.last_validated_at,
    )
