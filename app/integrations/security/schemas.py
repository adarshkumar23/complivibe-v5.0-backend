from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ScanJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scan_source: str
    scan_type: str
    status: str
    submitted_at: datetime
    completed_at: datetime | None
    total_findings: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    issues_created: int
    control_tests_created: int
    source_metadata: dict


class TrivyIngestResponse(BaseModel):
    scan_job_id: str
    scan_source: str
    total_findings: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    issues_created: int
    control_tests_created: int


class ProwlerIngestResponse(BaseModel):
    scan_job_id: str
    scan_source: str
    total_findings: int
    failed_count: int
    critical_count: int
    high_count: int
    issues_created: int
    control_tests_created: int


class OpenSCAPIngestResponse(BaseModel):
    scan_job_id: str
    scan_source: str
    total_findings: int
    failed_count: int
    critical_count: int
    high_count: int
    issues_created: int
    control_tests_created: int


class WazuhIngestResponse(BaseModel):
    scan_job_id: str
    scan_source: str
    total_alerts: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    issues_created: int
    control_tests_created: int


class FidesImportResponse(BaseModel):
    total_datasets: int
    assets_created: int
    assets_updated: int
    assets_skipped: int


class FidesImportStatusResponse(BaseModel):
    import_source: str
    asset_count: int
