import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProcessingActivityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    purpose: str = Field(min_length=1)
    legal_basis: str
    legitimate_interest_justification: str | None = None
    data_categories: list[str] = Field(default_factory=list)
    special_categories: list[str] = Field(default_factory=list)
    data_subject_types: list[str] = Field(default_factory=list)
    retention_period: str | None = Field(default=None, max_length=255)
    retention_basis: str | None = None
    recipients: list[str] = Field(default_factory=list)
    international_transfers: bool = False
    transfer_destinations: list[str] = Field(default_factory=list)
    transfer_safeguards: str | None = Field(default=None, max_length=100)
    controller_name: str | None = Field(default=None, max_length=255)
    controller_contact: str | None = Field(default=None, max_length=255)
    dpo_contact: str | None = Field(default=None, max_length=255)
    status: str = "active"
    risk_level: str | None = None
    requires_dpia: bool | None = None
    linked_dpia_id: uuid.UUID | None = None
    linked_data_asset_ids: list[str] = Field(default_factory=list)
    linked_subprocessor_ids: list[str] = Field(default_factory=list)
    owner_id: uuid.UUID


class ProcessingActivityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    purpose: str | None = None
    legal_basis: str | None = None
    legitimate_interest_justification: str | None = None
    data_categories: list[str] | None = None
    special_categories: list[str] | None = None
    data_subject_types: list[str] | None = None
    retention_period: str | None = Field(default=None, max_length=255)
    retention_basis: str | None = None
    recipients: list[str] | None = None
    international_transfers: bool | None = None
    transfer_destinations: list[str] | None = None
    transfer_safeguards: str | None = Field(default=None, max_length=100)
    controller_name: str | None = Field(default=None, max_length=255)
    controller_contact: str | None = Field(default=None, max_length=255)
    dpo_contact: str | None = Field(default=None, max_length=255)
    status: str | None = None
    risk_level: str | None = None
    requires_dpia: bool | None = None
    linked_dpia_id: uuid.UUID | None = None
    linked_data_asset_ids: list[str] | None = None
    linked_subprocessor_ids: list[str] | None = None
    owner_id: uuid.UUID | None = None


class ProcessingActivityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: str | None
    purpose: str
    legal_basis: str
    legitimate_interest_justification: str | None
    data_categories: list
    special_categories: list
    data_subject_types: list
    retention_period: str | None
    retention_basis: str | None
    recipients: list
    international_transfers: bool
    transfer_destinations: list
    transfer_safeguards: str | None
    controller_name: str | None
    controller_contact: str | None
    dpo_contact: str | None
    status: str
    risk_level: str | None
    requires_dpia: bool
    linked_dpia_id: uuid.UUID | None
    linked_data_asset_ids: list
    linked_subprocessor_ids: list
    owner_id: uuid.UUID
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class RopaFrameworkLinkCreate(BaseModel):
    obligation_id: uuid.UUID


class RopaFrameworkLinkRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    processing_activity_id: uuid.UUID
    obligation_id: uuid.UUID
    obligation_ref: str
    obligation_title: str
    framework_name: str
    linked_by: uuid.UUID
    linked_at: datetime


class RopaSummaryRead(BaseModel):
    total_activities: int
    by_status: dict[str, int]
    by_legal_basis: dict[str, int]
    requires_dpia_count: int
    with_international_transfers: int
    with_special_categories: int
    missing_dpia_count: int


class Article30ActivityRead(BaseModel):
    activity_id: str
    name: str
    purpose: str
    legal_basis: str
    data_categories: list
    special_categories: list
    data_subject_types: list
    retention_period: str | None
    recipients: list
    international_transfers: bool
    transfer_destinations: list
    transfer_safeguards: str | None


class Article30ReportRead(BaseModel):
    report_type: str
    status: str
    generated_at: str
    organization: dict
    activities: list[Article30ActivityRead]
    total_activities: int
    message: str | None = None
