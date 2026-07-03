from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

DORA_ASSESSMENT_FREQUENCY_PATTERN = "^(annual|biannual|quarterly|continuous)$"
DORA_STATUS_PATTERN = "^(active|under_review|terminated)$"


class DORAICTRegisterCreate(BaseModel):
    vendor_id: UUID | None = None
    counterparty_name: str = Field(min_length=1, max_length=255)
    service_description: str = Field(min_length=1)
    is_critical_function: bool = False
    sub_outsourcing_used: bool = False
    data_location: str | None = Field(default=None, max_length=200)
    data_location_countries: list[str] = Field(default_factory=list)
    contract_start_date: date | None = None
    contract_end_date: date | None = None
    exit_strategy_documented: bool = False
    exit_strategy_notes: str | None = None
    last_assessed_at: datetime | None = None
    assessment_frequency: str | None = Field(default=None, pattern=DORA_ASSESSMENT_FREQUENCY_PATTERN)
    dora_article: str = Field(default="Art.28", max_length=20)
    status: str = Field(default="active", pattern=DORA_STATUS_PATTERN)
    owner_id: UUID


class DORAICTRegisterUpdate(BaseModel):
    vendor_id: UUID | None = None
    counterparty_name: str | None = Field(default=None, min_length=1, max_length=255)
    service_description: str | None = None
    is_critical_function: bool | None = None
    sub_outsourcing_used: bool | None = None
    data_location: str | None = Field(default=None, max_length=200)
    data_location_countries: list[str] | None = None
    contract_start_date: date | None = None
    contract_end_date: date | None = None
    exit_strategy_documented: bool | None = None
    exit_strategy_notes: str | None = None
    last_assessed_at: datetime | None = None
    assessment_frequency: str | None = Field(default=None, pattern=DORA_ASSESSMENT_FREQUENCY_PATTERN)
    dora_article: str | None = Field(default=None, max_length=20)
    status: str | None = Field(default=None, pattern=DORA_STATUS_PATTERN)
    owner_id: UUID | None = None


class DORAICTRegisterRead(BaseModel):
    id: UUID
    organization_id: UUID
    vendor_id: UUID | None = None
    counterparty_name: str
    service_description: str
    is_critical_function: bool
    sub_outsourcing_used: bool
    data_location: str | None = None
    data_location_countries: list | dict
    contract_start_date: date | None = None
    contract_end_date: date | None = None
    exit_strategy_documented: bool
    exit_strategy_notes: str | None = None
    last_assessed_at: datetime | None = None
    assessment_frequency: str | None = Field(default=None, pattern=DORA_ASSESSMENT_FREQUENCY_PATTERN)
    dora_article: str
    status: str = Field(pattern=DORA_STATUS_PATTERN)
    owner_id: UUID
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class DORAICTRegisterReportRead(BaseModel):
    total_providers: int
    critical_function_count: int
    missing_exit_strategy: int
    assessment_overdue: int
    by_data_location: dict[str, int]
    sub_outsourcing_count: int
