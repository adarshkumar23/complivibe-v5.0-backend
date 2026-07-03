from uuid import UUID

from pydantic import BaseModel


class PolicyRiskLinkCreateRequest(BaseModel):
    risk_id: UUID
    link_reason: str | None = None


class PolicyRef(BaseModel):
    id: UUID
    title: str
    status: str


class RiskRef(BaseModel):
    id: UUID
    title: str
    status: str


class PolicyRiskLinkResponse(BaseModel):
    policy_id: UUID
    risk_id: UUID
    status: str
