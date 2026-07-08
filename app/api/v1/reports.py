from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path
import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.compliance.renderers.docx_report_renderer import DocxReportRenderer
from app.compliance.renderers.pdf_report_renderer import PDFReportRenderer
from app.compliance.services.framework_coverage_matrix_service import FrameworkCoverageMatrixService
from app.compliance.services.regulatory_report_service import RegulatoryReportService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.core.config import get_settings
from app.models.compliance_report import ComplianceReport
from app.models.compliance_report_section import ComplianceReportSection
from app.models.membership import Membership
from app.models.data_subject_request import DataSubjectRequest
from app.models.organization import Organization
from app.models.user import User
from app.repositories.report_repository import ReportRepository
from app.schemas.reports import (
    ComplianceReportDetail,
    ComplianceReportGenerateRequest,
    ComplianceReportGenerateResponse,
    ComplianceReportListResponse,
    ComplianceReportProvenanceResponse,
    ComplianceReportRead,
    ComplianceReportSectionRead,
    ComplianceReportSummary,
    FrameworkReadinessData,
    XBRLExportRequest,
    XBRLExportResponse,
)
from app.services.audit_service import AuditService
from app.services.export_service import ExportService
from app.services.report_service import ReportService
from app.compliance.services.board_scorecard_service import BoardScorecardService
from app.compliance.services.executive_narrative_service import ExecutiveNarrativeService
from app.compliance.services.xbrl_export_service import XBRLExportService

router = APIRouter(prefix="/reports", tags=["reports"])
compliance_router = APIRouter(prefix="/compliance/reports", tags=["compliance-reports"])


class FrameworkCoverageMatrixExportRequest(BaseModel):
    framework_id: uuid.UUID


def _report_read(service: ReportService, row: ComplianceReport) -> ComplianceReportRead:
    return ComplianceReportRead(**service.report_response_payload(row))


def _section_read(row: ComplianceReportSection) -> ComplianceReportSectionRead:
    return ComplianceReportSectionRead(
        id=row.id,
        organization_id=row.organization_id,
        report_id=row.report_id,
        section_key=row.section_key,
        title=row.title,
        body_markdown=row.body_markdown,
        data_json=row.data_json,
        provenance_json=row.provenance_json,
        sort_order=row.sort_order,
        created_at=row.created_at,
    )


@compliance_router.get("/regulatory/ccpa")
def get_ccpa_annual_report(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:read")),
):
    now = datetime.now(UTC)
    year_start = datetime(now.year, 1, 1, tzinfo=UTC)
    year_end = datetime(now.year + 1, 1, 1, tzinfo=UTC)

    base_filters = [
        DataSubjectRequest.organization_id == organization.id,
        DataSubjectRequest.regulatory_framework == "ccpa",
        DataSubjectRequest.deleted_at.is_(None),
        DataSubjectRequest.received_at >= year_start,
        DataSubjectRequest.received_at < year_end,
    ]

    requests_received = {
        "know": int(
            db.execute(select(func.count(DataSubjectRequest.id)).where(*base_filters, DataSubjectRequest.request_type == "access")).scalar_one()
            or 0
        ),
        "delete": int(
            db.execute(select(func.count(DataSubjectRequest.id)).where(*base_filters, DataSubjectRequest.request_type == "erasure")).scalar_one()
            or 0
        ),
        "opt_out": int(
            db.execute(select(func.count(DataSubjectRequest.id)).where(*base_filters, DataSubjectRequest.request_type == "opt_out_of_sale")).scalar_one()
            or 0
        ),
        "correct": int(
            db.execute(
                select(func.count(DataSubjectRequest.id)).where(*base_filters, DataSubjectRequest.request_type == "rectification")
            ).scalar_one()
            or 0
        ),
        "limit_sensitive": int(
            db.execute(
                select(func.count(DataSubjectRequest.id)).where(*base_filters, DataSubjectRequest.request_type == "limit_sensitive")
            ).scalar_one()
            or 0
        ),
    }

    fulfilled_filters = [
        *base_filters,
        DataSubjectRequest.status == "fulfilled",
        DataSubjectRequest.fulfilled_at.is_not(None),
    ]
    fulfilled_rows = db.execute(
        select(
            DataSubjectRequest.received_at,
            DataSubjectRequest.fulfilled_at,
            DataSubjectRequest.response_deadline,
        ).where(*fulfilled_filters)
    ).all()
    total_fulfilled = len(fulfilled_rows)

    within_deadline = sum(1 for row in fulfilled_rows if row.fulfilled_at <= row.response_deadline)
    if total_fulfilled > 0:
        avg_response_days = round(
            sum((row.fulfilled_at - row.received_at) / timedelta(days=1) for row in fulfilled_rows) / total_fulfilled,
            2,
        )
    else:
        avg_response_days = 0.0

    return {
        "report_type": "ccpa_annual",
        "reporting_year": now.year,
        "requests_received": requests_received,
        "response_metrics": {
            "within_deadline": within_deadline,
            "avg_response_days": avg_response_days,
            "total_fulfilled": total_fulfilled,
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }


@router.post("/generate", response_model=ComplianceReportGenerateResponse)
def generate_report(
    payload: ComplianceReportGenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:generate")),
) -> ComplianceReportGenerateResponse:
    service = ReportService(db)
    service.validate_reporting_period(payload.period_start, payload.period_end)
    sections, inputs_summary, provenance = service.build_report(
        organization_id=organization.id,
        report_type=payload.report_type,
        framework_id=payload.framework_id,
    )
    provenance = {
        **provenance,
        "generated_by_user_id": str(current_user.id),
        "organization_id": str(organization.id),
        "report_type": payload.report_type,
    }

    title = payload.title or f"{payload.report_type.replace('_', ' ').title()} Report"

    if payload.dry_run:
        report, section_rows = service.build_dry_run_report(
            organization_id=organization.id,
            report_type=payload.report_type,
            title=title,
            description=payload.description,
            framework_id=payload.framework_id,
            period_start=payload.period_start,
            period_end=payload.period_end,
            generated_by_user_id=current_user.id,
            sections=sections,
            inputs_summary=inputs_summary,
            provenance=provenance,
        )
    else:
        report, section_rows = service.persist_report(
            organization_id=organization.id,
            report_type=payload.report_type,
            title=title,
            description=payload.description,
            framework_id=payload.framework_id,
            period_start=payload.period_start,
            period_end=payload.period_end,
            generated_by_user_id=current_user.id,
            sections=sections,
            inputs_summary=inputs_summary,
            provenance=provenance,
        )

    AuditService(db).write_audit_log(
        action="report.generated",
        entity_type="compliance_report",
        entity_id=report.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "report_type": report.report_type,
            "dry_run": payload.dry_run,
            "status": report.status,
            "section_count": len(section_rows),
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    if payload.dry_run:
        db.flush()
    else:
        db.commit()
        db.refresh(report)
        for row in section_rows:
            db.refresh(row)

    return ComplianceReportGenerateResponse(
        dry_run=payload.dry_run,
        report=_report_read(service, report),
        sections=[_section_read(row) for row in section_rows],
    )


@router.get("/summary", response_model=ComplianceReportSummary)
def reports_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:read")),
) -> ComplianceReportSummary:
    return ComplianceReportSummary(**ReportService(db).summary(organization.id))


@router.get("/frameworks/{framework_id}/readiness", response_model=FrameworkReadinessData)
def framework_readiness_data(
    framework_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:read")),
) -> FrameworkReadinessData:
    data = ReportService(db).framework_readiness_data(organization.id, framework_id)
    return FrameworkReadinessData(**data)


@router.get("", response_model=ComplianceReportListResponse)
def list_reports(
    report_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    framework_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:read")),
) -> ComplianceReportListResponse:
    service = ReportService(db)
    rows = ReportRepository(db).list_reports(
        organization_id=organization.id,
        report_type=report_type,
        status=status_filter,
        framework_id=framework_id,
        limit=limit,
        offset=offset,
    )
    return ComplianceReportListResponse(reports=[_report_read(service, row) for row in rows])


@router.get("/regulatory/available-types")
def list_available_regulatory_report_types(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:read")),
):
    _ = db
    _ = organization
    return {"report_types": RegulatoryReportService.list_available_report_types()}


@router.post("/regulatory/{report_type}", response_model=ComplianceReportRead)
def generate_regulatory_report(
    report_type: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:read")),
) -> ComplianceReportRead:
    service = ReportService(db)
    report = RegulatoryReportService(db).generate_regulatory_report(
        org_id=organization.id,
        report_type=report_type,
        db=db,
        created_by=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="report.regulatory_generated",
        entity_type="compliance_report",
        entity_id=report.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"report_type": report_type, "report_id": str(report.id)},
        metadata_json={"source": "api", "report_type": report_type},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(report)
    return _report_read(service, report)


@router.get("/framework-coverage-matrix")
def get_framework_coverage_matrix(
    framework_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:read")),
):
    payload = FrameworkCoverageMatrixService(db).build(framework_id=framework_id, org_id=organization.id, db=db)
    AuditService(db).write_audit_log(
        action="report.coverage_matrix_generated",
        entity_type="framework",
        entity_id=framework_id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"framework_id": str(framework_id), "coverage_pct": payload.get("coverage_pct")},
        metadata_json={"source": "api"},
    )
    db.commit()
    return payload


@router.post("/framework-coverage-matrix/export-pdf")
def export_framework_coverage_matrix_pdf(
    payload: FrameworkCoverageMatrixExportRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:read")),
):
    matrix = FrameworkCoverageMatrixService(db).build(framework_id=payload.framework_id, org_id=organization.id, db=db)
    content = PDFReportRenderer().render_coverage_matrix(
        org_name=organization.name,
        framework_name=matrix.get("framework_name", "Framework"),
        matrix_payload=matrix,
    )
    checksum = hashlib.sha256(content).hexdigest()
    file_path = _report_export_path(organization_id=organization.id, report_id=payload.framework_id, extension="pdf")
    Path(file_path).write_bytes(content)

    job = ExportService(db).create_completed_binary_export_job(
        organization_id=organization.id,
        source_report_id=None,
        export_type="compliance_report_pdf",
        title="Framework Coverage Matrix PDF Export",
        description="Rendered PDF export for framework coverage matrix",
        file_path=file_path,
        file_format="pdf",
        file_size_bytes=len(content),
        checksum_sha256=checksum,
        requested_by_user_id=current_user.id,
    )

    AuditService(db).write_audit_log(
        action="report.coverage_matrix_generated",
        entity_type="framework",
        entity_id=payload.framework_id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"export_job_id": str(job.id), "framework_id": str(payload.framework_id)},
        metadata_json={"source": "api", "format": "pdf"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return StreamingResponse(
        iter([content]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=framework_coverage_{payload.framework_id}.pdf"},
    )



@router.get("/{report_id}", response_model=ComplianceReportDetail)
def report_detail(
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:read")),
) -> ComplianceReportDetail:
    service = ReportService(db)
    report = service.report_or_404(organization.id, report_id)
    sections = ReportRepository(db).list_sections(organization.id, report.id)
    return ComplianceReportDetail(report=_report_read(service, report), sections=[_section_read(row) for row in sections])


@router.get("/{report_id}/provenance", response_model=ComplianceReportProvenanceResponse)
def report_provenance(
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:read")),
) -> ComplianceReportProvenanceResponse:
    service = ReportService(db)
    report = service.report_or_404(organization.id, report_id)
    sections = ReportRepository(db).list_sections(organization.id, report.id)

    return ComplianceReportProvenanceResponse(
        report_id=report.id,
        provenance_json=report.provenance_json,
        section_provenance=[
            {
                "section_id": str(row.id),
                "section_key": row.section_key,
                "provenance_json": row.provenance_json or {},
            }
            for row in sections
        ],
    )


@router.post("/{report_id}/archive", response_model=ComplianceReportRead)
def archive_report(
    report_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:write")),
) -> ComplianceReportRead:
    service = ReportService(db)
    report = service.report_or_404(organization.id, report_id)
    if report.status == "archived":
        return _report_read(service, report)

    before_status = report.status

    report.status = "archived"
    report.archived_at = datetime.now(UTC)
    db.flush()

    AuditService(db).write_audit_log(
        action="report.archived",
        entity_type="compliance_report",
        entity_id=report.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json={"status": before_status},
        after_json={"status": report.status, "archived_at": report.archived_at.isoformat() if report.archived_at else None},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(report)
    return _report_read(service, report)


@router.post("/board-scorecard", response_model=ComplianceReportRead)
def generate_board_scorecard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:generate")),
) -> ComplianceReportRead:
    service = ReportService(db)
    report = BoardScorecardService(db).generate_board_scorecard(
        org_id=organization.id,
        created_by=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="report.board_scorecard_generated",
        entity_type="compliance_report",
        entity_id=report.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"report_type": report.report_type, "status": report.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(report)
    return _report_read(service, report)


@router.post("/executive-narrative", response_model=ComplianceReportRead)
def generate_executive_narrative(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:read")),
) -> ComplianceReportRead:
    service = ReportService(db)
    report = ExecutiveNarrativeService(db).generate_executive_narrative(
        org_id=organization.id,
        created_by=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="report.executive_narrative_generated",
        entity_type="compliance_report",
        entity_id=report.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"report_type": report.report_type, "status": report.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(report)
    return _report_read(service, report)


def _report_export_path(*, organization_id: uuid.UUID, report_id: uuid.UUID, extension: str) -> str:
    storage_root = Path(get_settings().FILE_STORAGE_PATH or "/tmp/complivibe_exports/").expanduser()
    export_dir = storage_root / "reports" / str(organization_id)
    export_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return str(export_dir / f"{report_id}_{timestamp}.{extension}")


@router.post("/{report_id}/export/pdf")
def export_report_pdf(
    report_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:read")),
):
    content = PDFReportRenderer().render(report_id=report_id, org_id=organization.id, db=db)
    checksum = hashlib.sha256(content).hexdigest()
    file_path = _report_export_path(organization_id=organization.id, report_id=report_id, extension="pdf")
    Path(file_path).write_bytes(content)

    job = ExportService(db).create_completed_binary_export_job(
        organization_id=organization.id,
        source_report_id=report_id,
        export_type="compliance_report_pdf",
        title="Compliance Report PDF Export",
        description="Rendered PDF export for compliance report",
        file_path=file_path,
        file_format="pdf",
        file_size_bytes=len(content),
        checksum_sha256=checksum,
        requested_by_user_id=current_user.id,
    )

    AuditService(db).write_audit_log(
        action="report.exported_pdf",
        entity_type="compliance_report",
        entity_id=report_id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "export_job_id": str(job.id),
            "checksum_sha256": checksum,
            "file_path": file_path,
            "format": "pdf",
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return StreamingResponse(
        iter([content]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=report_{report_id}.pdf"},
    )


@router.post("/{report_id}/export/docx")
def export_report_docx(
    report_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:read")),
):
    content = DocxReportRenderer().render(report_id=report_id, org_id=organization.id, db=db)
    checksum = hashlib.sha256(content).hexdigest()
    file_path = _report_export_path(organization_id=organization.id, report_id=report_id, extension="docx")
    Path(file_path).write_bytes(content)

    job = ExportService(db).create_completed_binary_export_job(
        organization_id=organization.id,
        source_report_id=report_id,
        export_type="compliance_report_docx",
        title="Compliance Report DOCX Export",
        description="Rendered DOCX export for compliance report",
        file_path=file_path,
        file_format="docx",
        file_size_bytes=len(content),
        checksum_sha256=checksum,
        requested_by_user_id=current_user.id,
    )

    AuditService(db).write_audit_log(
        action="report.exported_docx",
        entity_type="compliance_report",
        entity_id=report_id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "export_job_id": str(job.id),
            "checksum_sha256": checksum,
            "file_path": file_path,
            "format": "docx",
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename=report_{report_id}.docx"},
    )


@router.post("/{report_id}/xbrl-export", response_model=XBRLExportResponse)
def export_report_xbrl(
    report_id: uuid.UUID,
    payload: XBRLExportRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:xbrl_export")),
) -> XBRLExportResponse:
    job, xbrl_content, checksum, file_path = XBRLExportService(db).export_report(
        org_id=organization.id,
        report_id=report_id,
        payload=payload,
        requested_by_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="report.exported_xbrl",
        entity_type="compliance_report",
        entity_id=report_id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "export_job_id": str(job.id),
            "checksum_sha256": checksum,
            "file_path": file_path,
            "format": "xbrl",
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return XBRLExportResponse(
        report_id=report_id,
        export_job_id=job.id,
        validation_status="valid",
        validation_errors=[],
        checksum_sha256=checksum,
        file_path=file_path,
        xbrl_content=xbrl_content,
    )
