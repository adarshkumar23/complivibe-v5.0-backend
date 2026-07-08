from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import UUIDTimestampSchema

VENDOR_TYPE_PATTERN = "^(software|infrastructure|professional_services|data_processor|other)$"
VENDOR_RISK_TIER_PATTERN = "^(critical|high|medium|low|not_assessed)$"
VENDOR_STATUS_PATTERN = "^(active|under_review|inactive|archived)$"


class VendorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    vendor_type: str = Field(pattern=VENDOR_TYPE_PATTERN)
    website: str | None = Field(default=None, max_length=512)
    primary_contact_name: str | None = Field(default=None, max_length=255)
    primary_contact_email: EmailStr | None = None
    risk_tier: str = Field(default="not_assessed", pattern=VENDOR_RISK_TIER_PATTERN)
    status: str = Field(default="active", pattern=VENDOR_STATUS_PATTERN)
    owner_user_id: UUID
    data_access: bool = False
    processes_personal_data: bool = False
    sub_processor: bool = False
    tags_json: dict | list | None = None
    notes: str | None = None
    annual_spend_amount: Decimal | None = Field(default=None, ge=0)


class VendorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    vendor_type: str | None = Field(default=None, pattern=VENDOR_TYPE_PATTERN)
    website: str | None = Field(default=None, max_length=512)
    primary_contact_name: str | None = Field(default=None, max_length=255)
    primary_contact_email: EmailStr | None = None
    risk_tier: str | None = Field(default=None, pattern=VENDOR_RISK_TIER_PATTERN)
    status: str | None = Field(default=None, pattern=VENDOR_STATUS_PATTERN)
    owner_user_id: UUID | None = None
    data_access: bool | None = None
    processes_personal_data: bool | None = None
    sub_processor: bool | None = None
    tags_json: dict | list | None = None
    notes: str | None = None
    annual_spend_amount: Decimal | None = Field(default=None, ge=0)


class VendorArchiveRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class VendorRead(UUIDTimestampSchema):
    organization_id: UUID
    name: str
    description: str | None = None
    vendor_type: str
    website: str | None = None
    primary_contact_name: str | None = None
    primary_contact_email: str | None = None
    risk_tier: str
    status: str
    owner_user_id: UUID
    data_access: bool
    processes_personal_data: bool
    sub_processor: bool
    nth_party_risk_flag: bool
    nth_party_risk_severity: str | None = None
    nth_party_risk_signal_type: str | None = None
    nth_party_risk_updated_at: datetime | None = None
    tags_json: dict | list | None = None
    notes: str | None = None
    archived_at: datetime | None = None
    archived_by_user_id: UUID | None = None
    archive_reason: str | None = None
    has_overdue_assessment: bool = False
    risk_tier_source: str = "computed"
    annual_spend_amount: Decimal | None = None


class VendorSummary(BaseModel):
    total_vendors: int
    active_vendors: int
    archived_vendors: int
    by_status: dict[str, int]
    by_risk_tier: dict[str, int]
    by_vendor_type: dict[str, int]
