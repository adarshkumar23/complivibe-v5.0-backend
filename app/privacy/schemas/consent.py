import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConsentRecordCreate(BaseModel):
    processing_activity_id: uuid.UUID
    notice_id: uuid.UUID | None = None
    subject_identifier: str = Field(min_length=1, max_length=500)
    consent_mechanism: str
    consent_version: str | None = Field(default=None, max_length=50)
    granted: bool = True
    ip_address: str | None = Field(default=None, max_length=45)
    user_agent: str | None = None
    expiry_date: date | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConsentInboundEvent(ConsentRecordCreate):
    pass


class ConsentWithdrawRequest(BaseModel):
    reason: str | None = None


class ConsentStatusRead(BaseModel):
    has_consent: bool
    granted_at: datetime | None
    withdrawn_at: datetime | None
    consent_mechanism: str | None


class ConsentRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    processing_activity_id: uuid.UUID
    notice_id: uuid.UUID | None
    subject_identifier: str
    subject_identifier_hash: str
    consent_mechanism: str
    consent_version: str | None
    granted: bool
    granted_at: datetime | None
    withdrawn_at: datetime | None
    withdrawal_reason: str | None
    ip_address: str | None
    user_agent: str | None
    expiry_date: date | None
    metadata_json: dict
    created_at: datetime
    updated_at: datetime


class ConsentSummaryRead(BaseModel):
    total_records: int
    active_consents: int
    withdrawn_count: int
    expired_count: int
    consent_rate_pct: float
