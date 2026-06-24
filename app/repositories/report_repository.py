import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.compliance_report import ComplianceReport
from app.models.compliance_report_section import ComplianceReportSection


class ReportRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_report(self, report_id: uuid.UUID) -> ComplianceReport | None:
        return self.db.execute(select(ComplianceReport).where(ComplianceReport.id == report_id)).scalar_one_or_none()

    def list_reports(
        self,
        organization_id: uuid.UUID,
        *,
        report_type: str | None,
        status: str | None,
        framework_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> list[ComplianceReport]:
        stmt = select(ComplianceReport).where(ComplianceReport.organization_id == organization_id)
        if report_type:
            stmt = stmt.where(ComplianceReport.report_type == report_type)
        if status:
            stmt = stmt.where(ComplianceReport.status == status)
        if framework_id:
            stmt = stmt.where(ComplianceReport.framework_id == framework_id)

        return list(
            self.db.execute(
                stmt.order_by(ComplianceReport.generated_at.desc(), ComplianceReport.created_at.desc()).offset(offset).limit(limit)
            ).scalars().all()
        )

    def list_sections(self, organization_id: uuid.UUID, report_id: uuid.UUID) -> list[ComplianceReportSection]:
        return list(
            self.db.execute(
                select(ComplianceReportSection)
                .where(
                    ComplianceReportSection.organization_id == organization_id,
                    ComplianceReportSection.report_id == report_id,
                )
                .order_by(ComplianceReportSection.sort_order.asc(), ComplianceReportSection.created_at.asc())
            ).scalars().all()
        )
