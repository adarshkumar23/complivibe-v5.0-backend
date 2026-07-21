from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

COMMITMENT_TYPE_PATTERN = "^(breach_notification|subprocessor_notice|audit_right|data_deletion|data_portability|sla|security_assessment|custom)$"
#: The six precise types the P9 contract-extraction pipeline classifies. Finer
#: grained than COMMITMENT_TYPE_PATTERN, which stays core's coarse vocabulary.
P9_OBLIGATION_TYPE_PATTERN = (
    "^(breach_notification_sla|audit_right|data_deletion_timeline"
    "|subprocessor_restriction|data_residency_requirement|sla_commitment)$"
)
COMMITMENT_STATUS_PATTERN = "^(active|triggered|fulfilled|overdue|waived|expired)$"
NOTIFICATION_TYPE_PATTERN = "^(reminder|triggered|escalation|fulfilled)$"
TRIGGERED_BY_PATTERN = "^(scheduler|manual|api)$"


class CustomerCommitmentCreate(BaseModel):
    customer_name: str = Field(min_length=1, max_length=255)
    customer_email: str | None = Field(default=None, max_length=255)
    commitment_type: str = Field(pattern=COMMITMENT_TYPE_PATTERN)
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    trigger_condition: str = Field(min_length=1)
    triggering_incident_type: str | None = Field(default=None, max_length=100)
    trigger_date: date | None = None
    notification_days_before: int = Field(default=7, ge=1, le=90)
    sla_hours: int | None = None
    linked_contract_ref: str | None = Field(default=None, max_length=500)
    assigned_owner_id: UUID


class CustomerCommitmentUpdate(BaseModel):
    customer_name: str | None = Field(default=None, min_length=1, max_length=255)
    customer_email: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    trigger_condition: str | None = None
    triggering_incident_type: str | None = Field(default=None, max_length=100)
    trigger_date: date | None = None
    notification_days_before: int | None = Field(default=None, ge=1, le=90)
    sla_hours: int | None = None
    linked_contract_ref: str | None = Field(default=None, max_length=500)
    assigned_owner_id: UUID | None = None


class CustomerCommitmentFulfillRequest(BaseModel):
    notes: str | None = None


class CustomerCommitmentWaiveRequest(BaseModel):
    reason: str = Field(min_length=1)


class CustomerCommitmentRead(BaseModel):
    id: UUID
    organization_id: UUID
    customer_name: str
    customer_email: str | None = None
    commitment_type: str = Field(pattern=COMMITMENT_TYPE_PATTERN)
    title: str
    description: str
    trigger_condition: str
    triggering_incident_type: str | None = None
    trigger_date: date | None = None
    notification_days_before: int
    sla_hours: int | None = None
    status: str = Field(pattern=COMMITMENT_STATUS_PATTERN)
    linked_contract_ref: str | None = None
    assigned_owner_id: UUID
    triggered_at: datetime | None = None
    fulfilled_at: datetime | None = None
    fulfilled_by: UUID | None = None
    fulfillment_notes: str | None = None
    waived_at: datetime | None = None
    waived_by: UUID | None = None
    waiver_reason: str | None = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None

    # P9 contract-extraction provenance (migration 0327). NULL on every
    # human-created commitment; populated only via the P9 ingest route.
    obligation_type: str | None = Field(default=None, pattern=P9_OBLIGATION_TYPE_PATTERN)
    extracted_params: dict[str, Any] | None = None
    confidence_score: Decimal | None = Field(default=None, ge=0, le=1)
    requires_human_review: bool = False
    source_clause_text: str | None = None


class CommitmentNotificationLogRead(BaseModel):
    id: UUID
    organization_id: UUID
    commitment_id: UUID
    notification_type: str = Field(pattern=NOTIFICATION_TYPE_PATTERN)
    queued_at: datetime
    recipient_user_ids: list | dict
    message_preview: str | None = None
    triggered_by: str = Field(pattern=TRIGGERED_BY_PATTERN)


class CommitmentTriggerSweepResult(BaseModel):
    reminders: int
    triggered: int
    overdue: int
    notifications_queued: int


class BreachSlaComplianceRead(BaseModel):
    total_breach_commitments: int
    fulfilled_within_sla: int
    breached_sla: int
    compliance_rate: float


class CustomerCommitmentDashboard(BaseModel):
    total: int
    by_type: dict[str, int]
    by_status: dict[str, int]
    overdue_count: int
    triggered_count: int
    due_within_30_days: int
    fulfilled_this_month: int
    breach_notification_sla_compliance: BreachSlaComplianceRead
