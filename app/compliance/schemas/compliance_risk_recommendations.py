from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ComplianceRiskRecommendationGenerateRequest(BaseModel):
    business_unit_id: uuid.UUID | None = None


class ComplianceRiskRecommendationRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    business_unit_id: uuid.UUID | None
    recommendation_type: str
    title: str
    rationale: str
    suggested_category: str | None
    suggested_likelihood: int | None
    suggested_impact: int | None
    suggested_treatment: str | None
    linked_risk_id: uuid.UUID | None
    context_snapshot_json: dict[str, Any]
    provider_used: str
    used_byo_credentials: bool
    status: str
    accepted_risk_id: uuid.UUID | None
    generated_by: uuid.UUID
    accepted_by: uuid.UUID | None
    dismissed_by: uuid.UUID | None
    snoozed_until: datetime | None
    created_at: datetime
    updated_at: datetime


class ComplianceRiskRecommendationListResponse(BaseModel):
    items: list[ComplianceRiskRecommendationRead]
    total: int
    page: int
    page_size: int


class ComplianceRiskRecommendationSnoozeRequest(BaseModel):
    snoozed_until: datetime


class ComplianceRiskRecommendationActionResponse(BaseModel):
    id: uuid.UUID
    status: str
    accepted_risk_id: uuid.UUID | None = None


class ComplianceRiskRecommendationAcceptResponse(BaseModel):
    recommendation: ComplianceRiskRecommendationRead
    created_or_updated_risk_id: uuid.UUID | None


class ComplianceRiskRecommendationGenerateResponse(BaseModel):
    items: list[ComplianceRiskRecommendationRead] = Field(default_factory=list)
