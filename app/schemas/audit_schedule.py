from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import UUIDTimestampSchema

AUDIT_TYPE_PATTERN = "^(internal_readiness|external_certification|surveillance|gap_assessment)$"
SCHEDULE_STATUS_PATTERN = "^(active|paused|cancelled)$"
RECURRENCE_PATTERN = "^(annual|semi_annual|quarterly|monthly)$"


class AuditScheduleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    audit_type: str = Field(pattern=AUDIT_TYPE_PATTERN)
    framework_id: UUID
    recurrence_pattern: str = Field(pattern=RECURRENCE_PATTERN)
    next_audit_date: date
    preparation_reminder_days: int = Field(default=30, ge=7, le=90)


class AuditScheduleUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    next_audit_date: date | None = None
    preparation_reminder_days: int | None = Field(default=None, ge=7, le=90)
    recurrence_pattern: str | None = Field(default=None, pattern=RECURRENCE_PATTERN)


class AuditScheduleStatusRequest(BaseModel):
    new_status: str = Field(pattern=SCHEDULE_STATUS_PATTERN)


class AuditScheduleLinkEngagementRequest(BaseModel):
    engagement_id: UUID


class AuditScheduleRead(UUIDTimestampSchema):
    organization_id: UUID
    title: str
    audit_type: str = Field(pattern=AUDIT_TYPE_PATTERN)
    framework_id: UUID
    recurrence_pattern: str = Field(pattern=RECURRENCE_PATTERN)
    next_audit_date: date
    preparation_reminder_days: int
    last_reminder_sent_at: datetime | None = None
    last_audit_engagement_id: UUID | None = None
    status: str = Field(pattern=SCHEDULE_STATUS_PATTERN)
    created_by: UUID


class AuditScheduleReminderSweepResult(BaseModel):
    processed: int
    reminders_sent: int
    calendars_created: int
