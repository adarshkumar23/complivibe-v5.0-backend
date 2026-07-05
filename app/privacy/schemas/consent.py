import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


GCM_V2_CONSENT_STATES = {"granted", "denied"}


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


class GoogleConsentModeV2Create(BaseModel):
    subject_identifier: str = Field(min_length=1, max_length=500)
    domain: str = Field(min_length=1, max_length=255)
    url: str | None = None
    region: str | None = Field(default=None, max_length=50)
    client_id: str | None = Field(default=None, max_length=255)
    session_id: str | None = Field(default=None, max_length=255)
    event_name: str = Field(default="consent_update", min_length=1, max_length=100)
    event_timestamp: datetime | None = None
    ad_storage: str
    analytics_storage: str
    ad_user_data: str
    ad_personalization: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("ad_storage", "analytics_storage", "ad_user_data", "ad_personalization")
    @classmethod
    def validate_gcm_state(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in GCM_V2_CONSENT_STATES:
            allowed = ", ".join(sorted(GCM_V2_CONSENT_STATES))
            raise ValueError(f"Google Consent Mode v2 state must be one of: {allowed}")
        return normalized


class GoogleConsentModeV2StatusRead(BaseModel):
    has_signal: bool
    domain: str
    region: str | None
    ad_storage: str | None
    analytics_storage: str | None
    ad_user_data: str | None
    ad_personalization: str | None
    last_event_at: datetime | None
    is_stale: bool
    stale_after_days: int
    regional_default_expected: str | None
    default_state_risk: bool
    default_state_risk_detail: str | None


class GoogleConsentModeV2Read(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    subject_identifier_hash: str
    domain: str
    url: str | None
    region: str | None
    client_id: str | None
    session_id: str | None
    gcm_version: str
    event_name: str
    event_timestamp: datetime | None
    ad_storage: str
    analytics_storage: str
    ad_user_data: str
    ad_personalization: str
    raw_payload_json: dict
    created_by_user_id: uuid.UUID | None
    created_at: datetime
