from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampSchema


class EvidenceControlSummary(BaseModel):
    control_id: UUID
    title: str
    status: str


class EvidenceControlLinkRead(UUIDTimestampSchema):
    organization_id: UUID
    evidence_item_id: UUID
    control_id: UUID
    link_status: str
    confidence: str
    rationale: str | None = None
    linked_by_user_id: UUID | None = None
    linked_at: datetime | None = None
    unlinked_at: datetime | None = None


class EvidenceRead(UUIDTimestampSchema):
    organization_id: UUID
    title: str
    description: str | None = None
    evidence_type: str
    source: str
    status: str
    review_status: str
    freshness_status: str
    file_name: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    checksum_sha256: str | None = None
    storage_provider: str | None = None
    storage_key: str | None = None
    external_reference_url: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    collected_at: datetime | None = None
    original_created_at: datetime | None = None
    uploaded_by_user_id: UUID | None = None
    reviewed_by_user_id: UUID | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = None
    metadata_json: dict | None = None


class EvidenceDetail(EvidenceRead):
    linked_controls: list[EvidenceControlSummary]


class EvidenceCreate(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str | None = None
    evidence_type: str = Field(default="other")
    source: str = Field(default="manual")
    file_name: str | None = Field(default=None, max_length=255)
    mime_type: str | None = Field(default=None, max_length=255)
    size_bytes: int | None = Field(default=None, ge=0)
    checksum_sha256: str | None = Field(default=None, max_length=128)
    external_reference_url: str | None = Field(default=None, max_length=1024)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    collected_at: datetime | None = None
    metadata_json: dict | None = None


class EvidenceUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = None
    evidence_type: str | None = None
    source: str | None = None
    status: str | None = Field(default=None, pattern="^(active|archived|deleted_pending|superseded)$")
    file_name: str | None = Field(default=None, max_length=255)
    mime_type: str | None = Field(default=None, max_length=255)
    size_bytes: int | None = Field(default=None, ge=0)
    checksum_sha256: str | None = Field(default=None, max_length=128)
    external_reference_url: str | None = Field(default=None, max_length=1024)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    collected_at: datetime | None = None
    metadata_json: dict | None = None


class EvidenceControlLinkCreate(BaseModel):
    control_id: UUID
    confidence: str = Field(default="manual_confirmed", pattern="^(manual_confirmed|system_suggested|imported|low_confidence)$")
    rationale: str | None = None


class EvidenceReviewRequest(BaseModel):
    review_status: str = Field(pattern="^(verified|rejected|needs_review)$")
    review_notes: str | None = None


class EvidenceReadinessSummary(BaseModel):
    total_evidence_items: int
    verified_evidence_items: int
    needs_review_evidence_items: int
    rejected_evidence_items: int
    expired_evidence_items: int
    controls_with_verified_evidence: int
    controls_without_evidence: int
    controls_with_expired_evidence: int


class EvidenceControlGap(BaseModel):
    control_id: UUID
    control_name: str
    reason: str = Field(description="never_linked | linked_but_expired | linked_but_rejected | linked_but_not_reviewed")


class EvidenceControlGapPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[EvidenceControlGap]
