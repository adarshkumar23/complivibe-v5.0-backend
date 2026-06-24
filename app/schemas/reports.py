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
