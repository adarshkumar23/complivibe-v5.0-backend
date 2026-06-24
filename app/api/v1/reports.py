from datetime import UTC, datetime
import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.compliance_report import ComplianceReport
from app.models.compliance_report_section import ComplianceReportSection
from app.models.membership import Membership
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
)
from app.services.audit_service import AuditService
from app.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])


def _report_read(row: ComplianceReport) -> ComplianceReportRead:
    return ComplianceReportRead(
        id=row.id,
        organization_id=row.organization_id,
        report_type=row.report_type,
        title=row.title,
        description=row.description,
        status=row.status,
        framework_id=row.framework_id,
        period_start=row.period_start,
        period_end=row.period_end,
        generated_by_user_id=row.generated_by_user_id,
        generated_at=row.generated_at,
        archived_at=row.archived_at,
        content_json=row.content_json,
        content_markdown=row.content_markdown,
        provenance_json=row.provenance_json,
        inputs_summary_json=row.inputs_summary_json,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


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
        report=_report_read(report),
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
    rows = ReportRepository(db).list_reports(
        organization_id=organization.id,
        report_type=report_type,
        status=status_filter,
        framework_id=framework_id,
        limit=limit,
        offset=offset,
    )
    return ComplianceReportListResponse(reports=[_report_read(row) for row in rows])


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
    return ComplianceReportDetail(report=_report_read(report), sections=[_section_read(row) for row in sections])


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
    return _report_read(report)
