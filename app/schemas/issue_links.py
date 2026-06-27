from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class IssuePolicyLinkCreate(BaseModel):
    policy_id: UUID
    link_type: str = Field(pattern="^(violated|related)$")


class IssuePolicyLinkRead(BaseModel):
    id: UUID
    organization_id: UUID
    issue_id: UUID
    policy_id: UUID
    link_type: str
    linked_by: UUID
    linked_at: datetime


class IssueControlLinkCreate(BaseModel):
    control_id: UUID
    failure_type: str = Field(pattern="^(control_absent|control_failed|control_bypassed|control_ineffective)$")


class IssueControlLinkRead(BaseModel):
    id: UUID
    organization_id: UUID
    issue_id: UUID
    control_id: UUID
    failure_type: str
    linked_by: UUID
    linked_at: datetime


class PolicyAssociatedIssueRead(BaseModel):
    issue_id: UUID
    title: str
    severity: str
    status: str
    link_type: str
    linked_at: datetime


class PolicyViolationRateRead(BaseModel):
    policy_id: UUID
    policy_name: str
    total_issues_past_12m: int
    violations_past_12m: int
    violation_rate: float


class ControlAssociatedIssueRead(BaseModel):
    issue_id: UUID
    title: str
    severity: str
    status: str
    failure_type: str
    linked_at: datetime


class ControlAssociatedIssuesGroupedRead(BaseModel):
    control_id: UUID
    grouped: dict[str, list[ControlAssociatedIssueRead]]


class ControlFailureRateRead(BaseModel):
    control_id: UUID
    control_name: str
    active_months: int
    total_failures: int
    failure_rate: float
    by_failure_type: dict[str, int]
    open_high_critical_count: int
