from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

ATTESTATION_TOKEN_ENTITY_TYPE_PATTERN = "^(export_attestation|export_job|ai_system_governance_attestation)$"
ATTESTATION_TOKEN_STATUS_PATTERN = "^(active|revoked|expired)$"


class AttestationTokenCreateRequest(BaseModel):
    purpose: str = Field(min_length=1, max_length=64)
    scope: dict | None = None
    linked_entity_type: str = Field(pattern=ATTESTATION_TOKEN_ENTITY_TYPE_PATTERN)
    linked_entity_id: UUID
    expires_at: datetime


class AttestationTokenCreateResponse(BaseModel):
    token_id: UUID
    organization_id: UUID
    purpose: str
    linked_entity_type: str = Field(pattern=ATTESTATION_TOKEN_ENTITY_TYPE_PATTERN)
    linked_entity_id: UUID
    expires_at: datetime
    plaintext_token: str
    warning: str


class AttestationTokenValidationResponse(BaseModel):
    token_id: UUID
    organization_id: UUID
    purpose: str
    scope: dict
    linked_entity_type: str = Field(pattern=ATTESTATION_TOKEN_ENTITY_TYPE_PATTERN)
    linked_entity_id: UUID
    status: str = Field(pattern=ATTESTATION_TOKEN_STATUS_PATTERN)
    expires_at: datetime
    validation_count: int
    last_validated_at: datetime | None = None
