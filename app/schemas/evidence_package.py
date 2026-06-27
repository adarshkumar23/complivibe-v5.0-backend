from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampSchema

PACKAGE_STATUS_PATTERN = "^(draft|assembled|exported|archived)$"


class EvidencePackageCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    scope_framework_ids: list[UUID] = Field(default_factory=list)


class EvidencePackageAddItem(BaseModel):
    control_id: UUID
    evidence_id: UUID
    framework_requirement_ref: str | None = Field(default=None, max_length=255)


class EvidencePackageRead(UUIDTimestampSchema):
    organization_id: UUID
    audit_engagement_id: UUID
    title: str
    scope_framework_ids: list[UUID]
    cover_sheet_data: dict
    chain_of_custody: list[dict]
    status: str = Field(pattern=PACKAGE_STATUS_PATTERN)
    assembled_at: datetime | None = None
    assembled_by: UUID | None = None
    exported_at: datetime | None = None
    item_count: int


class EvidencePackageItemRead(BaseModel):
    id: UUID
    package_id: UUID
    organization_id: UUID
    control_id: UUID
    evidence_id: UUID
    framework_requirement_ref: str | None = None
    display_order: int
    added_at: datetime
    added_by: UUID


class EvidencePackageManifestItem(BaseModel):
    item_id: UUID
    control_id: UUID
    control_name: str
    evidence_id: UUID
    evidence_title: str
    display_order: int


class EvidencePackageManifest(BaseModel):
    package: dict
    items_by_framework_ref: dict[str, list[EvidencePackageManifestItem]]
    items_ungrouped: list[EvidencePackageManifestItem]
    chain_of_custody: list[dict]
