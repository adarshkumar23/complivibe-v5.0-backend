from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

LICENSE_TYPE_PATTERN = "^(public_domain|creative_commons|commercial_license|proprietary_internal|unclear|none)$"
CONSENT_BASIS_PATTERN = "^(explicit_consent|legitimate_interest|contractual|statutory|not_applicable|unclear)$"
RIGHTS_STATUS_PATTERN = "^(active|expired|revoked)$"
RIGHTS_STATUS_VALUES = ["active", "expired", "revoked"]

LICENSE_TYPE_VALUES = [
    "public_domain",
    "creative_commons",
    "commercial_license",
    "proprietary_internal",
    "unclear",
    "none",
]
CONSENT_BASIS_VALUES = [
    "explicit_consent",
    "legitimate_interest",
    "contractual",
    "statutory",
    "not_applicable",
    "unclear",
]

# License types / consent bases treated as "not documented" for rights-gap purposes.
UNCLEAR_LICENSE_TYPES = {"unclear", "none"}
UNCLEAR_CONSENT_BASES = {"unclear", None}


class TrainingDatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    source: str | None = Field(default=None, max_length=500)
    license_type: str = Field(default="unclear", pattern=LICENSE_TYPE_PATTERN)
    consent_basis: str | None = Field(default=None, pattern=CONSENT_BASIS_PATTERN)
    linked_ai_system_id: UUID
    record_count: int | None = Field(default=None, ge=0)
    notes: str | None = None
    rights_status: str = Field(default="active", pattern=RIGHTS_STATUS_PATTERN)
    rights_expires_at: date | None = None


class TrainingDatasetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    source: str | None = Field(default=None, max_length=500)
    license_type: str | None = Field(default=None, pattern=LICENSE_TYPE_PATTERN)
    consent_basis: str | None = Field(default=None, pattern=CONSENT_BASIS_PATTERN)
    linked_ai_system_id: UUID | None = None
    record_count: int | None = Field(default=None, ge=0)
    notes: str | None = None
    rights_status: str | None = Field(default=None, pattern=RIGHTS_STATUS_PATTERN)
    rights_expires_at: date | None = None


class TrainingDatasetResponse(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    source: str | None = None
    license_type: str
    consent_basis: str | None = None
    linked_ai_system_id: UUID
    record_count: int | None = None
    notes: str | None = None
    created_by: UUID | None = None
    rights_status: str
    rights_expires_at: date | None = None
    deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AISystemRightsGapRef(BaseModel):
    id: UUID
    name: str


class TrainingDataRightsGaps(BaseModel):
    total_ai_systems: int
    documented_count: int
    unclear_rights_count: int
    no_dataset_linked_count: int
    rights_lapsed_count: int
    no_dataset_linked: list[AISystemRightsGapRef]
    unclear_rights: list[AISystemRightsGapRef]
    rights_lapsed: list[AISystemRightsGapRef]
