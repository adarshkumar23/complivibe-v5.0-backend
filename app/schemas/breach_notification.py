from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

BREACH_TYPE_PATTERN = "^(personal_data|financial|health|confidential)$"
BREACH_FRAMEWORK_PATTERN = "^(gdpr|dora|nis2|hipaa|ccpa|dpdp)$"
BREACH_STATUS_PATTERN = "^(assessing|notification_due|regulator_notified|subjects_notified|closed)$"


class BreachNotificationCreate(BaseModel):
    breach_type: str = Field(pattern=BREACH_TYPE_PATTERN)
    personal_data_affected: bool = False
    estimated_affected_count: int | None = Field(default=None, ge=0)
    regulatory_notification_required: bool = False
    regulatory_framework: str | None = Field(default="gdpr", pattern=BREACH_FRAMEWORK_PATTERN)
    regulatory_notification_hours: int = Field(default=72, ge=1)
    supervisory_authority: str | None = Field(default=None, max_length=255)
    subject_notification_required: bool = False


class BreachNotificationRead(BaseModel):
    id: UUID
    organization_id: UUID
    issue_id: UUID
    breach_type: str = Field(pattern=BREACH_TYPE_PATTERN)
    personal_data_affected: bool
    estimated_affected_count: int | None = None
    regulatory_notification_required: bool
    regulatory_framework: str | None = Field(default=None, pattern=BREACH_FRAMEWORK_PATTERN)
    regulatory_notification_hours: int
    regulatory_notification_deadline: datetime | None = None
    supervisory_authority: str | None = None
    regulatory_notified_at: datetime | None = None
    subject_notification_required: bool
    subjects_notified_at: datetime | None = None
    data_subjects_affected_count: int | None = None
    special_category_data_involved: bool = False
    article33_notification_text: str | None = None
    article34_required: bool = False
    subjects_notification_text: str | None = None
    dpa_reference_number: str | None = None
    status: str = Field(pattern=BREACH_STATUS_PATTERN)
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class BreachDeadlineSweepResult(BaseModel):
    warned: int
    transitioned: int


class BreachPrivacyFieldsUpdate(BaseModel):
    data_subjects_affected_count: int | None = Field(default=None, ge=0)
    special_category_data_involved: bool | None = None
    article33_notification_text: str | None = None
    article34_required: bool | None = None
    subjects_notification_text: str | None = None
    dpa_reference_number: str | None = Field(default=None, max_length=100)


class BreachGenerateArticle33DraftRead(BaseModel):
    draft_text: str
    used_ai: bool = False


class BreachRecordArticle33SentRequest(BaseModel):
    sent_to: str | None = Field(default=None, max_length=255)


class BreachRecordSubjectsNotifiedRequest(BaseModel):
    count: int | None = Field(default=None, ge=0)
