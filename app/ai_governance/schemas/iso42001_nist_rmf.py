import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ISO42001TrackerUpdateRequest(BaseModel):
    status: str
    notes: str | None = None
    evidence_id: uuid.UUID | None = None


class ISO42001TrackerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    clause_ref: str
    implementation_status: str
    evidence_id: uuid.UUID | None
    notes: str | None
    updated_by: uuid.UUID | None
    updated_at: datetime
    created_at: datetime


class ISO42001SummaryRead(BaseModel):
    total_clauses: int
    by_status: dict[str, int]
    implementation_pct: float
    sections: dict[str, dict[str, int | float]]


class NISTRMFSubcategoryUpdateRequest(BaseModel):
    subcategory_ref: str
    response_status: str
    notes: str | None = None
    evidence_id: uuid.UUID | None = None


class NISTRMFImplementationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    ai_system_id: uuid.UUID
    govern_status: str
    map_status: str
    measure_status: str
    manage_status: str
    last_updated_at: datetime
    created_by: uuid.UUID
    created_at: datetime


class NISTRMFFunctionResponseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    implementation_id: uuid.UUID
    function: str
    subcategory_ref: str
    response_status: str
    notes: str | None
    evidence_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class NISTRMFImplementationDetailRead(BaseModel):
    implementation: NISTRMFImplementationRead
    responses: list[NISTRMFFunctionResponseRead]


class NISTRMFMaturityRead(BaseModel):
    govern: dict[str, int | float]
    map: dict[str, int | float]
    measure: dict[str, int | float]
    manage: dict[str, int | float]
    overall_maturity_pct: float
    implementation_id: str | None = None


class NISTRMFOrgSummaryRead(BaseModel):
    govern: dict[str, int | float]
    map: dict[str, int | float]
    measure: dict[str, int | float]
    manage: dict[str, int | float]
    overall_maturity_pct: float
    systems_count: int
