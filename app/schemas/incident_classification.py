from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


CATEGORY_PATTERN = "^(security_breach|privacy_violation|service_disruption|data_corruption|unauthorized_access|insider_threat|third_party_failure|regulatory_event)$"


class IncidentClassificationOverrideRequest(BaseModel):
    category: str = Field(pattern=CATEGORY_PATTERN)
    sub_category: str | None = None
    regulatory_implications: list[str] = Field(default_factory=list)


class IncidentClassificationRead(BaseModel):
    id: UUID
    organization_id: UUID
    issue_id: UUID
    category: str
    sub_category: str | None
    regulatory_implications: list[str]
    notification_required: bool
    auto_classified: bool
    classification_by: UUID
    classified_at: datetime
    last_updated_at: datetime
    # True when the linked issue's type/severity has changed since this
    # classification was derived -- category/notification_required may no
    # longer reflect the issue as it stands today.
    stale: bool = False


class IncidentAnalyticsRead(BaseModel):
    total_classified: int
    by_category: dict[str, int]
    notification_required_count: int
    regulatory_breakdown: dict[str, int]
