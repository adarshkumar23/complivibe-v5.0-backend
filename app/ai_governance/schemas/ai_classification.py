import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GuidedClassificationStartRead(BaseModel):
    questions: list[dict[str, str]]


class GuidedClassificationSubmitRequest(BaseModel):
    answers: dict[str, str]


class ManualClassificationRequest(BaseModel):
    risk_tier: str
    notes: str | None = None


class AIRiskClassificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    ai_system_id: uuid.UUID
    risk_tier: str
    classification_method: str
    classification_basis: dict[str, Any]
    classified_by: uuid.UUID
    classified_at: datetime
    review_required_at: datetime | None
    updated_at: datetime
    classification_explanation: str | None = Field(
        default=None,
        description="Human-readable explanation of why this risk tier was assigned.",
    )
    reassessment_required: bool = Field(
        default=False,
        description=(
            "True when the AI system's registered attributes were changed after this "
            "classification was recorded, meaning the tier may no longer be accurate."
        ),
    )


class MandatoryControlsRead(BaseModel):
    mandatory_controls: list[str]


class EUAIActClassifyRequest(BaseModel):
    article_category: str
    annex_reference: str | None = None
    conformity_route: str | None = None


class EUAIActClassificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    ai_system_id: uuid.UUID
    article_category: str
    annex_reference: str | None
    conformity_route: str | None
    registration_required: bool
    transparency_obligations: list[str]
    classified_by: uuid.UUID
    classified_at: datetime
    updated_at: datetime


class EUActAnnexMappingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    annex_ref: str
    annex_type: str
    sector: str
    description: str
    article_refs: list[str]
    is_active: bool


class EUAIActObligationRead(BaseModel):
    id: uuid.UUID
    reference_code: str
    title: str
    description: str | None
