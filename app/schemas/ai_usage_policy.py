from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

COMPLIANCE_STATUS_VALUES = (
    "compliant",
    "non_compliant_no_policy",
    "non_compliant_expired_attestation",
    "non_compliant_never_attested",
    "not_applicable",
)


class AiUsagePolicyCheckResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    ai_system_id: UUID
    policy_id: UUID | None = None
    compliance_status: str
    last_checked_at: datetime
    details: str | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class AiUsagePolicyRunResponse(BaseModel):
    checked_count: int
    results: list[AiUsagePolicyCheckResponse]


class AiUsagePolicySummaryResponse(BaseModel):
    total_checked: int
    by_status: dict[str, int]


class AiUsagePolicyGapItem(BaseModel):
    ai_system_id: UUID
    ai_system_name: str
    policy_id: UUID | None = None
    compliance_status: str
    reason: str
    last_checked_at: datetime


class AiUsagePolicyGapsResponse(BaseModel):
    total_gaps: int
    gaps: list[AiUsagePolicyGapItem]
