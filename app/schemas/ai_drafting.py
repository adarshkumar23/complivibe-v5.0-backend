from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


DRAFT_TYPE_PATTERN = (
    "^(policy_content|risk_description|control_description|evidence_description|rca_summary|"
    "ai_risk_assessment_narrative|model_card_content|eu_act_conformity_narrative|ai_policy_draft)$"
)


class OrgAIConfigRead(BaseModel):
    id: UUID
    organization_id: UUID
    ai_drafting_enabled: bool
    enabled_by: UUID | None = None
    enabled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class DraftApplyRequest(BaseModel):
    target_entity_type: str = Field(min_length=1, max_length=100)
    target_entity_id: UUID


class DraftRequestRead(BaseModel):
    id: UUID
    organization_id: UUID
    draft_type: str = Field(pattern=DRAFT_TYPE_PATTERN)
    context_json: dict
    draft_output: str | None = None
    model_used: str | None = None
    prompt_used: str | None = None
    created_by: UUID
    applied: bool
    applied_at: datetime | None = None
    applied_by: UUID | None = None
    truncated: bool = Field(
        default=False,
        description=(
            "True when the AI completion was cut off by the token budget before "
            "finishing (finish_reason == 'length'). draft_output will end mid-sentence "
            "in that case; treat it as incomplete rather than a finished document."
        ),
    )
    created_at: datetime
    updated_at: datetime


class PolicyContentDraftRequest(BaseModel):
    policy_type: str = Field(min_length=1, max_length=255)
    scope_description: str | None = None
    framework_context: str | None = None


class RiskDescriptionDraftRequest(BaseModel):
    risk_title: str = Field(min_length=1, max_length=255)
    risk_category: str | None = None
    linked_control_titles: list[str] = Field(default_factory=list)


class ControlDescriptionDraftRequest(BaseModel):
    control_name: str = Field(min_length=1, max_length=255)
    control_type: str | None = None
    framework_ref: str | None = None


class EvidenceDescriptionDraftRequest(BaseModel):
    evidence_title: str = Field(min_length=1, max_length=255)
    control_name: str | None = None
    evidence_type: str | None = None


class RCASummaryDraftRequest(BaseModel):
    issue_title: str = Field(min_length=1, max_length=255)
    issue_type: str | None = None
    timeline_description: str | None = None


class AIRiskAssessmentNarrativeDraftRequest(BaseModel):
    ai_system_id: UUID


class ModelCardContentDraftRequest(BaseModel):
    ai_system_id: UUID


class EUActConformityNarrativeDraftRequest(BaseModel):
    system_name: str = Field(min_length=1, max_length=255)
    article_category: str | None = Field(default="high_risk_annex3", max_length=100)
    conformity_route: str | None = Field(default="self_assessment", max_length=100)


class AIPolicyDraftRequest(BaseModel):
    industry: str | None = Field(default="technology", max_length=100)
    policy_scope: str | None = Field(default="all AI systems", max_length=255)
    key_risks: str | None = None
