import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DPACreate(BaseModel):
    counterparty_name: str = Field(min_length=1, max_length=255)
    counterparty_type: str
    vendor_id: uuid.UUID | None = None
    subprocessor_id: uuid.UUID | None = None
    dpa_reference: str | None = Field(default=None, max_length=500)
    status: str = "pending"
    signed_date: date | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    auto_renews: bool = False
    renewal_notice_days: int = Field(default=30, ge=0)
    governing_regulation: list[str] = Field(default_factory=list)
    article28_compliant: bool | None = None
    sccs_included: bool | None = None
    bcrs_included: bool | None = None
    data_transfer_countries: list[str] = Field(default_factory=list)
    processing_activity_ids: list[str] = Field(default_factory=list)
    review_notes: str | None = None
    owner_id: uuid.UUID


class DPAUpdate(BaseModel):
    counterparty_name: str | None = Field(default=None, min_length=1, max_length=255)
    counterparty_type: str | None = None
    vendor_id: uuid.UUID | None = None
    subprocessor_id: uuid.UUID | None = None
    dpa_reference: str | None = Field(default=None, max_length=500)
    status: str | None = None
    signed_date: date | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    auto_renews: bool | None = None
    renewal_notice_days: int | None = Field(default=None, ge=0)
    governing_regulation: list[str] | None = None
    article28_compliant: bool | None = None
    sccs_included: bool | None = None
    bcrs_included: bool | None = None
    data_transfer_countries: list[str] | None = None
    processing_activity_ids: list[str] | None = None
    review_notes: str | None = None
    owner_id: uuid.UUID | None = None


class DPAStatusTransition(BaseModel):
    new_status: str


class DPALinkActivityRequest(BaseModel):
    activity_id: uuid.UUID


class DPARead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    counterparty_name: str
    counterparty_type: str
    vendor_id: uuid.UUID | None
    subprocessor_id: uuid.UUID | None
    dpa_reference: str | None
    status: str
    signed_date: date | None
    effective_date: date | None
    expiry_date: date | None
    auto_renews: bool
    renewal_notice_days: int
    governing_regulation: list[Any]
    article28_compliant: bool | None
    sccs_included: bool | None
    bcrs_included: bool | None
    data_transfer_countries: list[Any]
    processing_activity_ids: list[Any]
    review_notes: str | None
    owner_id: uuid.UUID
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class DPASummaryRead(BaseModel):
    total: int
    by_status: dict[str, int]
    by_type: dict[str, int]
    article28_compliant_count: int
    missing_dpa_count: int
    expiring_soon_30d: int
    gdpr_coverage: dict[str, Any]
