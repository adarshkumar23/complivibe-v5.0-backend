from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PolicyIssueLinkCreateRequest(BaseModel):
    issue_id: UUID
    link_reason: str | None = None


class PolicyIssueLinkResponse(BaseModel):
    issue_id: UUID
    policy_id: UUID
    status: str
    link_reason: str | None = None


class PolicyIssueRef(BaseModel):
    id: UUID
    title: str
    status: str
    severity: str
    issue_type: str
    created_at: datetime


class PolicyRef(BaseModel):
    id: UUID
    title: str
    status: str
