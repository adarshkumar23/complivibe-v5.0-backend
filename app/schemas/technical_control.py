from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

TARGET_RESOURCE_PATTERN = "^(aws_s3|aws_iam|aws_ec2|aws_rds|gcp_iam|gcp_storage|azure_ad|azure_storage|network|os|generic)$"
EVALUATION_OPERATOR_PATTERN = "^(equals|not_equals|contains|not_contains|gte|lte|is_true|is_false|exists|not_exists)$"
SEVERITY_PATTERN = "^(info|warning|critical)$"


class TechnicalControlAgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class TechnicalControlAgentResponse(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    description: str | None = None
    is_active: bool
    last_seen_at: datetime | None = None
    created_at: datetime


class TechnicalControlAgentRegistrationResponse(TechnicalControlAgentResponse):
    token: str


class TechnicalControlRuleCreate(BaseModel):
    control_id: UUID
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    target_resource_type: str = Field(pattern=TARGET_RESOURCE_PATTERN)
    expected_config_key: str = Field(min_length=1, max_length=255)
    expected_config_value: str
    evaluation_operator: str = Field(pattern=EVALUATION_OPERATOR_PATTERN)
    severity: str = Field(default="warning", pattern=SEVERITY_PATTERN)


class TechnicalControlRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    target_resource_type: str | None = Field(default=None, pattern=TARGET_RESOURCE_PATTERN)
    expected_config_key: str | None = Field(default=None, min_length=1, max_length=255)
    expected_config_value: str | None = None
    evaluation_operator: str | None = Field(default=None, pattern=EVALUATION_OPERATOR_PATTERN)
    severity: str | None = Field(default=None, pattern=SEVERITY_PATTERN)
    is_active: bool | None = None


class TechnicalControlRuleControlRef(BaseModel):
    id: UUID
    name: str


class TechnicalControlRuleResponse(BaseModel):
    id: UUID
    organization_id: UUID
    control_id: UUID
    name: str
    description: str | None = None
    target_resource_type: str
    expected_config_key: str
    expected_config_value: str
    evaluation_operator: str
    severity: str
    is_active: bool
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    control: TechnicalControlRuleControlRef


class TechnicalControlResultIngestRequest(BaseModel):
    rule_id: UUID
    resource_identifier: str | None = None
    actual_config_key: str = Field(min_length=1, max_length=255)
    actual_config_value: str | None = None
    raw_payload: dict = Field(default_factory=dict)


class TechnicalControlResultRuleRef(BaseModel):
    id: UUID
    name: str
    severity: str


class TechnicalControlResultResponse(BaseModel):
    id: UUID
    organization_id: UUID
    rule_id: UUID
    agent_id: UUID
    resource_identifier: str | None = None
    actual_config_key: str
    actual_config_value: str | None = None
    raw_payload: dict
    passed: bool
    failure_reason: str | None = None
    control_test_run_id: UUID | None = None
    evaluated_at: datetime
    created_at: datetime
    rule: TechnicalControlResultRuleRef


class TechnicalControlRuleSummaryResponse(BaseModel):
    rule_id: UUID
    rule_name: str
    last_result: str = Field(pattern="^(passed|failed|never_run)$")
    pass_rate_7d: float | None = None
    pass_rate_30d: float | None = None
    total_checks: int
    last_checked_at: datetime | None = None
    last_failed_at: datetime | None = None
    last_passed_at: datetime | None = None


class TechnicalControlOrgSummaryResponse(BaseModel):
    total_rules: int
    active_rules: int
    checks_last_7d: int
    pass_rate_7d: float | None = None
    failing_rules: list[TechnicalControlRuleSummaryResponse]


class TechnicalControlIngestResponse(BaseModel):
    result_id: UUID
    rule_id: UUID
    passed: bool
    failure_reason: str | None = None
    evaluated_at: datetime
    control_test_run_id: UUID | None = None


class TechnicalControlResultFilters(BaseModel):
    rule_id: UUID | None = None
    agent_id: UUID | None = None
    passed: bool | None = None
    from_date: date | None = None
    control_id: UUID | None = None
