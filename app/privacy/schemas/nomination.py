import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NominationCreate(BaseModel):
    subject_identifier: str = Field(min_length=1, max_length=500)
    activation_trigger: str
    nominee_user_id: uuid.UUID | None = None
    nominee_name: str | None = Field(default=None, max_length=255)
    nominee_contact: str | None = Field(default=None, max_length=255)


class NominationRevokeRequest(BaseModel):
    reason: str | None = None


class NominationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    subject_identifier_hash: str
    nominee_user_id: uuid.UUID | None
    nominee_name: str | None
    nominee_contact: str | None
    activation_trigger: str
    status: str
    activated_at: datetime | None
    revoked_at: datetime | None
    revocation_reason: str | None
    created_at: datetime
    updated_at: datetime
