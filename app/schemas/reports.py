from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ComplianceReportGenerateRequest(BaseModel):
    report_type: str
    title: str | None = None
    description: str | None = None
    framework_id: UUID | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None
    dry_run: bool = False


class ComplianceReportSectionRead(BaseModel):
    id: UUID
    organization_id: UUID
    report_id: UUID
    section_key: str
    title: str
    body_markdown: str
    data_json: dict | None = None
    provenance_json: dict | None = None
    sort_order: int
    created_at: datetime


class ComplianceReportRead(BaseModel):
    id: UUID
    organization_id: UUID
    report_type: str
    title: str
    description: str | None = None
    status: str
    framework_id: UUID | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None
    generated_by_user_id: UUID | None = None
    generated_at: datetime
    archived_at: datetime | None = None
    content_json: dict
    content_markdown: str | None = None
    provenance_json: dict
    inputs_summary_json: dict | None = None
    age_days: int
    section_count: int
    is_archived: bool
    is_stale: bool
    context_flags: list[str]
    created_at: datetime
    updated_at: datetime


class ComplianceReportGenerateResponse(BaseModel):
    dry_run: bool
    report: ComplianceReportRead
    sections: list[ComplianceReportSectionRead]


class ComplianceReportDetail(BaseModel):
    report: ComplianceReportRead
    sections: list[ComplianceReportSectionRead]


class ComplianceReportListResponse(BaseModel):
    reports: list[ComplianceReportRead]


class ComplianceReportProvenanceResponse(BaseModel):
    report_id: UUID
    provenance_json: dict
    section_provenance: list[dict]


class ComplianceReportSummary(BaseModel):
    total_reports: int
    generated_reports: int
    archived_reports: int
    reports_last_30d: int
    stale_reports_30d: int
    archived_ratio: float
    context_flags: list[str]
    latest_executive_summary_at: datetime | None = None
    latest_framework_readiness_at: datetime | None = None
    latest_risk_posture_at: datetime | None = None


class FrameworkReadinessData(BaseModel):
    framework_id: UUID
    active_obligations: int
    applicable_obligations: int
    obligations_with_controls: int
    obligations_without_controls: int
    controls_total: int
    controls_implemented: int
    controls_with_verified_evidence: int
    risks_linked: int
    open_tasks: int
    latest_score_snapshots: list[dict]


class ReportListQuery(BaseModel):
    report_type: str | None = None
    status: str | None = None
    framework_id: UUID | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class XBRLDataPoint(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    taxonomy_concept: str = Field(min_length=3, max_length=255)
    value: str | int | float | bool
    period_start: datetime | None = None
    period_end: datetime | None = None
    instant: datetime | None = None
    unit: str | None = Field(default=None, max_length=64)
    decimals: int | None = Field(default=None, ge=-12, le=12)
    dimensions: dict[str, str] | None = None


class XBRLExportRequest(BaseModel):
    entity_identifier: str = Field(min_length=1, max_length=255)
    taxonomy_namespace: str = Field(
        default="https://xbrl.ifrs.org/taxonomy/2024-04-26/ifrs-sds",
        min_length=8,
        max_length=500,
    )
    taxonomy_schema_url: str = Field(
        default="https://xbrl.ifrs.org/taxonomy/ifrs_sds/2024-04-26/ifrs_sds_2024-04-26.xsd",
        min_length=8,
        max_length=500,
    )
    taxonomy_prefix: str = Field(default="ifrs-sds", min_length=1, max_length=20)
    data_points: list[XBRLDataPoint] = Field(min_length=1, max_length=500)


class XBRLValidationError(BaseModel):
    data_point_index: int | None = None
    field: str
    message: str


class XBRLExportResponse(BaseModel):
    report_id: UUID
    export_job_id: UUID
    validation_status: str
    validation_errors: list[XBRLValidationError]
    checksum_sha256: str
    file_path: str
    xbrl_content: str
