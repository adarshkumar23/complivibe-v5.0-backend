from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

SUBPROCESSOR_LEGAL_BASIS_PATTERN = "^(contract|legitimate_interest|consent|legal_obligation|vital_interests|public_task)$"
SUBPROCESSOR_TRANSFER_MECHANISM_PATTERN = "^(sccs|adequacy_decision|bcrs|derogation|not_applicable)$"
SUBPROCESSOR_DPA_STATUS_PATTERN = "^(pending|signed|not_required|expired|under_review)$"
SUBPROCESSOR_CONTROLLER_TYPE_PATTERN = "^(processor|sub_processor|joint_controller)$"
SUBPROCESSOR_RISK_LEVEL_PATTERN = "^(low|medium|high|critical)$"
SUBPROCESSOR_STATUS_PATTERN = "^(active|inactive|under_review|offboarded)$"


class SubprocessorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    service_description: str = Field(min_length=1)
    data_types_processed: list[str] = Field(default_factory=list)
    legal_basis: str = Field(pattern=SUBPROCESSOR_LEGAL_BASIS_PATTERN)
    geographic_locations: list[str] = Field(default_factory=list)
    data_transfer_mechanism: str | None = Field(default=None, pattern=SUBPROCESSOR_TRANSFER_MECHANISM_PATTERN)
    dpa_status: str = Field(default="pending", pattern=SUBPROCESSOR_DPA_STATUS_PATTERN)
    dpa_signed_at: datetime | None = None
    dpa_expiry_date: date | None = None
    dpa_document_ref: str | None = Field(default=None, max_length=500)
    controller_type: str = Field(pattern=SUBPROCESSOR_CONTROLLER_TYPE_PATTERN)
    risk_level: str = Field(default="medium", pattern=SUBPROCESSOR_RISK_LEVEL_PATTERN)
    status: str = Field(default="active", pattern=SUBPROCESSOR_STATUS_PATTERN)
    contact_name: str | None = Field(default=None, max_length=255)
    contact_email: str | None = Field(default=None, max_length=255)
    review_due_date: date | None = None


class SubprocessorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    service_description: str | None = None
    data_types_processed: list[str] | None = None
    legal_basis: str | None = Field(default=None, pattern=SUBPROCESSOR_LEGAL_BASIS_PATTERN)
    geographic_locations: list[str] | None = None
    data_transfer_mechanism: str | None = Field(default=None, pattern=SUBPROCESSOR_TRANSFER_MECHANISM_PATTERN)
    dpa_signed_at: datetime | None = None
    dpa_expiry_date: date | None = None
    dpa_document_ref: str | None = Field(default=None, max_length=500)
    controller_type: str | None = Field(default=None, pattern=SUBPROCESSOR_CONTROLLER_TYPE_PATTERN)
    risk_level: str | None = Field(default=None, pattern=SUBPROCESSOR_RISK_LEVEL_PATTERN)
    status: str | None = Field(default=None, pattern=SUBPROCESSOR_STATUS_PATTERN)
    contact_name: str | None = Field(default=None, max_length=255)
    contact_email: str | None = Field(default=None, max_length=255)
    review_due_date: date | None = None


class SubprocessorDpaStatusUpdate(BaseModel):
    new_status: str = Field(pattern=SUBPROCESSOR_DPA_STATUS_PATTERN)
    signed_at: datetime | None = None
    expiry_date: date | None = None


class SubprocessorDataTransferCreate(BaseModel):
    origin_country: str = Field(min_length=2, max_length=2)
    destination_country: str = Field(min_length=2, max_length=2)
    data_categories: list[str] = Field(default_factory=list)
    transfer_mechanism: str = Field(min_length=1, max_length=100)
    legal_basis: str = Field(min_length=1, max_length=100)
    is_active: bool = True
    notes: str | None = None


class SubprocessorRead(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    service_description: str
    data_types_processed: list | dict
    legal_basis: str
    geographic_locations: list | dict
    data_transfer_mechanism: str | None = None
    dpa_status: str = Field(pattern=SUBPROCESSOR_DPA_STATUS_PATTERN)
    dpa_signed_at: datetime | None = None
    dpa_expiry_date: date | None = None
    dpa_document_ref: str | None = None
    controller_type: str = Field(pattern=SUBPROCESSOR_CONTROLLER_TYPE_PATTERN)
    risk_level: str = Field(pattern=SUBPROCESSOR_RISK_LEVEL_PATTERN)
    status: str = Field(pattern=SUBPROCESSOR_STATUS_PATTERN)
    contact_name: str | None = None
    contact_email: str | None = None
    review_due_date: date | None = None
    last_reviewed_at: datetime | None = None
    last_reviewed_by: UUID | None = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class SubprocessorDataTransferRead(BaseModel):
    id: UUID
    organization_id: UUID
    subprocessor_id: UUID
    origin_country: str
    destination_country: str
    data_categories: list | dict
    transfer_mechanism: str
    legal_basis: str
    is_active: bool
    notes: str | None = None
    created_at: datetime


class SubprocessorSweepResult(BaseModel):
    expiring_soon: int
    expired: int
    reminders_queued: int


class SubprocessorGdprDashboard(BaseModel):
    total_subprocessors: int
    by_status: dict[str, int]
    by_dpa_status: dict[str, int]
    by_risk_level: dict[str, int]
    missing_dpa_count: int
    high_risk_count: int
    transfers_outside_eea: int
    review_overdue_count: int
    expiring_dpa_30_days: int
