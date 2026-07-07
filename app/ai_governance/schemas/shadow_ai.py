import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class ShadowAIReportCreate(BaseModel):
    detected_name: str = Field(min_length=1, max_length=255)
    notes: str | None = None


class ShadowAIDetectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    detected_name: str
    detection_method: str
    confidence: str
    status: str
    detected_at: datetime
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    notes: str | None
    registered_system_id: uuid.UUID | None
    reported_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    detection_reason: str = Field(
        default="",
        description=(
            "Human-readable explanation of the detection signal: how the tool was "
            "discovered and how confident the system is in the finding."
        ),
    )
    days_since_detected: int = Field(
        default=0,
        description="Number of days since this shadow AI tool was first detected.",
    )

    @classmethod
    def from_row(cls, row) -> "ShadowAIDetectionRead":
        method_explanations = {
            "manual_report": "Manually reported by a user via the shadow AI report endpoint",
            "questionnaire": (
                "Flagged from free-text answers in a compliance questionnaire that "
                "matched a known AI tool keyword"
            ),
            "integration_analysis": "Flagged by analyzing connected third-party integrations",
            "network_scan": "Flagged from network/egress traffic analysis to an unregistered AI endpoint",
        }
        base_reason = method_explanations.get(
            row.detection_method,
            f"Flagged via detection method '{row.detection_method}'",
        )
        reason = f"{base_reason}; confidence level: {row.confidence}."
        detected_at = row.detected_at
        if detected_at.tzinfo is None:
            detected_at = detected_at.replace(tzinfo=UTC)
        days_since = max(0, (datetime.now(UTC) - detected_at).days)

        data = cls.model_validate(row).model_dump()
        data["detection_reason"] = reason
        data["days_since_detected"] = days_since
        return cls(**data)


class ShadowAIReviewRequest(BaseModel):
    pass


class ShadowAIDismissRequest(BaseModel):
    notes: str | None = None
