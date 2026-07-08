from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampSchema

RISK_DEPENDENCY_RELATIONSHIP_PATTERN = "^(cascades_to|triggers|compounds)$"


class RiskDependencyCreate(BaseModel):
    downstream_risk_id: UUID
    relationship_type: str = Field(default="cascades_to", pattern=RISK_DEPENDENCY_RELATIONSHIP_PATTERN)
    rationale: str | None = None


class RiskDependencyRead(UUIDTimestampSchema):
    organization_id: UUID
    upstream_risk_id: UUID
    downstream_risk_id: UUID
    relationship_type: str
    rationale: str | None = None
    created_by_user_id: UUID | None = None


class RiskDependencyNode(BaseModel):
    risk_id: UUID
    title: str
    status: str
    severity: str
    category: str
    inherent_score: int
    residual_score: int | None = None


class RiskDependencyEdge(BaseModel):
    id: UUID
    upstream_risk_id: UUID
    downstream_risk_id: UUID
    relationship_type: str


class RiskDependencyGraph(BaseModel):
    root_risk_id: UUID
    nodes: list[RiskDependencyNode]
    edges: list[RiskDependencyEdge]
    summary: dict[str, int]
