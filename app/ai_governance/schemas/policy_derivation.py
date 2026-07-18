import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.ai_governance.services.policy_derivation.derivation_engine import ObligationRecord


class ObligationIn(BaseModel):
    id: str = Field(min_length=1, max_length=255)
    text: str = Field(min_length=1)
    jurisdiction: str | None = None
    framework: str | None = None
    citation: str | None = None
    control_ids: list[str] = []

    def to_record(self) -> ObligationRecord:
        return ObligationRecord(
            id=self.id,
            text=self.text,
            jurisdiction=self.jurisdiction,
            framework=self.framework,
            citation=self.citation,
            control_ids=tuple(self.control_ids),
        )


class DerivedGuardrailCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    obligations: list[ObligationIn] = Field(min_length=1)


class DerivedGuardrailRecompile(BaseModel):
    obligations: list[ObligationIn] = Field(min_length=1)


class CheckActionRequest(BaseModel):
    # Passthrough action dict; the envelope/payload split is enforced by
    # services.policy_derivation.envelope.build_envelope (payload-shaped fields
    # are rejected with HTTP 400).
    model_config = ConfigDict(extra="allow")


class DerivedGuardrailRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    ai_system_id: uuid.UUID
    name: str
    description: str | None
    rego_package: str
    rego_policy: str
    source_obligation_ids: list
    constraint_spec_json: dict
    compiled_at: datetime | None
    is_active: bool


class CheckActionResponse(BaseModel):
    allowed: bool
    reason: str
    receipt_id: str | None


class ReceiptRead(BaseModel):
    receipt_id: str
    timestamp: str
    envelope_hash: str
    decision: str
    reasons: list[str]
    previous_receipt_hash: str | None
    signature: str
    receipt_hash: str
    public_key_hex: str


class ReceiptChainRead(BaseModel):
    ai_system_id: uuid.UUID
    receipts: list[ReceiptRead]


class ChainVerificationResponse(BaseModel):
    passed: bool
    verified_count: int
    failure_index: int | None
    failure_reason: str | None
