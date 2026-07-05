from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

VERIFICATION_STATUS_VALUES = ("valid", "invalid")
INVALID_REASON_VALUES = (
    "missing_signature",
    "malformed_claim",
    "unsupported_version",
    "tampered_signature",
)


class ContentManifestVerifyRequest(BaseModel):
    content_identifier: str = Field(min_length=1, max_length=500)
    manifest: dict = Field(default_factory=dict)


class ContentProvenanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    content_identifier: str
    raw_manifest: dict
    verification_status: str
    invalid_reason: str | None = None
    spec_version_detected: str | None = None
    claim_generator: str | None = None
    assertion_count: int | None = None
    verified_at: datetime
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime
