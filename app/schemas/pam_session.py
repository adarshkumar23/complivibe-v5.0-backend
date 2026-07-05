from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

APPROVAL_STATUS_PATTERN = "^(approved|missing|denied|unknown)$"
RISK_STATUS_PATTERN = "^(monitor|open|accepted|resolved)$"


class PAMSessionIngestRequest(BaseModel):
    external_session_id: str = Field(min_length=1, max_length=255)
    pam_provider: str | None = Field(default=None, max_length=120)
    identity: str = Field(min_length=1, max_length=255)
    privileged_account: str | None = Field(default=None, max_length=255)
    target_system: str = Field(min_length=1, max_length=255)
    target_resource_type: str | None = Field(default=None, max_length=120)
    started_at: datetime
    ended_at: datetime | None = None
    approved_by: str | None = Field(default=None, max_length=255)
    approval_reference: str | None = Field(default=None, max_length=255)
    session_recording_url: str | None = None
    approval_status: str | None = Field(default=None, pattern=APPROVAL_STATUS_PATTERN)
    risk_status: str | None = Field(default=None, pattern=RISK_STATUS_PATTERN)
    raw_payload: dict = Field(default_factory=dict)


class PAMSessionUpdateRequest(BaseModel):
    ended_at: datetime | None = None
    approved_by: str | None = Field(default=None, max_length=255)
    approval_reference: str | None = Field(default=None, max_length=255)
    session_recording_url: str | None = None
    approval_status: str | None = Field(default=None, pattern=APPROVAL_STATUS_PATTERN)
    risk_status: str | None = Field(default=None, pattern=RISK_STATUS_PATTERN)
    risk_reason: str | None = None


class PAMSessionRead(BaseModel):
    id: UUID
    organization_id: UUID
    external_session_id: str
    pam_provider: str | None = None
    identity: str
    privileged_account: str | None = None
    target_system: str
    target_resource_type: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    approved_by: str | None = None
    approval_reference: str | None = None
    session_recording_url: str | None = None
    approval_status: str
    risk_status: str
    risk_reason: str | None = None
    source: str
    raw_payload: dict
    ingested_at: datetime
    created_at: datetime
    updated_at: datetime
    flagged_by: UUID | None = None
    flagged_at: datetime | None = None

    model_config = {"from_attributes": True}


class PAMSessionIngestResponse(BaseModel):
    session_id: UUID
    external_session_id: str
    approval_status: str
    risk_status: str
    risk_reason: str | None = None
    created: bool


class PAMUnapprovedRiskSummary(BaseModel):
    total_unapproved_sessions: int
    open_risk_sessions: int
    sessions: list[PAMSessionRead]
