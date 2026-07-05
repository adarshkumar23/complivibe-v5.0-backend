from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import UUIDTimestampSchema


class SodConflictRuleCreate(BaseModel):
    permission_a: str = Field(min_length=1, max_length=120)
    permission_b: str = Field(min_length=1, max_length=120)
    severity: str = Field(default="medium", min_length=1, max_length=32)
    description: str | None = Field(default=None, max_length=500)


class SodConflictRuleUpdate(BaseModel):
    permission_a: str | None = Field(default=None, min_length=1, max_length=120)
    permission_b: str | None = Field(default=None, min_length=1, max_length=120)
    severity: str | None = Field(default=None, min_length=1, max_length=32)
    active: bool | None = None
    status: str | None = Field(default=None, min_length=1, max_length=32)
    description: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_some_change(self) -> "SodConflictRuleUpdate":
        if not any(value is not None for value in self.model_dump().values()):
            raise ValueError("At least one field must be provided")
        return self


class SodConflictRuleRead(UUIDTimestampSchema):
    organization_id: UUID
    permission_a: str
    permission_b: str
    severity: str
    active: bool
    status: str
    description: str | None = None
    created_by: UUID | None = None
    updated_by: UUID | None = None


class SodConflictFindingRead(UUIDTimestampSchema):
    organization_id: UUID
    user_id: UUID
    rule_id: UUID
    permission_a: str | None = None
    permission_b: str | None = None
    severity: str | None = None
    detected_at: datetime
    status: str
    acknowledged_at: datetime | None = None
    acknowledged_by: UUID | None = None
    waived_at: datetime | None = None
    waived_by: UUID | None = None
    note: str | None = None


class SodConflictFindingAction(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class SodConflictDetectionResponse(BaseModel):
    user_id: UUID
    created_finding_ids: list[UUID]
    permission_codes: list[str]
