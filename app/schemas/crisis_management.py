from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

SCENARIO_TYPES = (
    "cyber_incident",
    "natural_disaster",
    "pandemic",
    "financial_crisis",
    "supply_chain_disruption",
    "data_breach",
    "regulatory_action",
    "reputational_crisis",
    "other",
)
PLAYBOOK_STATUSES = ("active", "archived", "draft")
ACTIVATION_STATUSES = ("active", "resolved", "cancelled")


class CrisisPlaybookCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    scenario_type: str
    trigger_conditions_json: list[dict] | dict | None = None
    steps_json: list[dict]
    owner_team: str | None = None
    status: str = "active"

    @field_validator("scenario_type")
    @classmethod
    def _validate_scenario_type(cls, value: str) -> str:
        if value not in SCENARIO_TYPES:
            raise ValueError(f"scenario_type must be one of {SCENARIO_TYPES}")
        return value

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        if value not in PLAYBOOK_STATUSES:
            raise ValueError(f"status must be one of {PLAYBOOK_STATUSES}")
        return value

    @field_validator("steps_json")
    @classmethod
    def _validate_steps(cls, value: list[dict]) -> list[dict]:
        if not value:
            raise ValueError("steps_json must contain at least one step")
        for item in value:
            if "step" not in item and "description" not in item:
                raise ValueError("each step entry requires a 'step' or 'description' key")
        return value


class CrisisPlaybookUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    scenario_type: str | None = None
    trigger_conditions_json: list[dict] | dict | None = None
    steps_json: list[dict] | None = None
    owner_team: str | None = None
    status: str | None = None

    @field_validator("scenario_type")
    @classmethod
    def _validate_scenario_type(cls, value: str | None) -> str | None:
        if value is not None and value not in SCENARIO_TYPES:
            raise ValueError(f"scenario_type must be one of {SCENARIO_TYPES}")
        return value

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: str | None) -> str | None:
        if value is not None and value not in PLAYBOOK_STATUSES:
            raise ValueError(f"status must be one of {PLAYBOOK_STATUSES}")
        return value

    @field_validator("steps_json")
    @classmethod
    def _validate_steps(cls, value: list[dict] | None) -> list[dict] | None:
        if value is None:
            return value
        if not value:
            raise ValueError("steps_json must contain at least one step")
        for item in value:
            if "step" not in item and "description" not in item:
                raise ValueError("each step entry requires a 'step' or 'description' key")
        return value


class CrisisPlaybookRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    scenario_type: str
    trigger_conditions_json: list[dict] | dict | None
    steps_json: list[dict]
    owner_team: str | None
    status: str
    created_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CrisisActivationResolveRequest(BaseModel):
    resolution_notes: str | None = None


class CrisisActivationRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    playbook_id: uuid.UUID
    activated_by_user_id: uuid.UUID | None
    activated_at: datetime
    status: str
    resolution_notes: str | None
    resolved_at: datetime | None
    resolved_by_user_id: uuid.UUID | None
    linked_processes_json: list[dict] | None
    linked_risks_json: list[dict] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CrisisActiveActivationItem(BaseModel):
    activation: CrisisActivationRead
    playbook_name: str
    scenario_type: str
