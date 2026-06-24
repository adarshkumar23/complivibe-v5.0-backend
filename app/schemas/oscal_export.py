from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

EXPORT_TYPE_PATTERN = "^(ssp|assessment_plan|assessment_results|full_package)$"
EXPORT_STATUS_PATTERN = "^(pending|processing|complete|failed)$"


class OSCALExportCreate(BaseModel):
    export_type: str = Field(pattern=EXPORT_TYPE_PATTERN)
    framework_id: UUID | None = None


class OSCALExportJobRead(BaseModel):
    id: UUID
    organization_id: UUID
    export_type: str
    framework_id: UUID | None = None
    status: str
    oscal_version: str
    result_size_bytes: int | None = None
    error_message: str | None = None
    requested_by_user_id: UUID
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class OSCALExportJobDetail(OSCALExportJobRead):
    result_json: dict | None = None


class OSCALValidateResponse(BaseModel):
    valid: bool
    errors: list[str]
    oscal_version: str
    export_type: str
    validated_at: datetime


class OSCALExportSummary(BaseModel):
    total_exports: int
    by_type: dict[str, int]
    by_status: dict[str, int]
    last_export_at: datetime | None = None
    last_successful_export_at: datetime | None = None
