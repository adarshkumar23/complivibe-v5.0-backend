import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class OrgEmailConfigUpsertRequest(BaseModel):
    aws_access_key_id: str = Field(min_length=1)
    aws_secret_access_key: str = Field(min_length=1)
    region: str = Field(min_length=1, max_length=64)
    from_address: EmailStr
    is_active: bool = True


class OrgEmailConfigStatusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID | None = None
    organization_id: uuid.UUID
    provider: str
    is_active: bool
    test_sent_at: datetime | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    config_configured: bool


class OrgEmailConfigTestRequest(BaseModel):
    to_address: EmailStr | None = None


class OrgEmailConfigTestResponse(BaseModel):
    success: bool
    sent_to: str
