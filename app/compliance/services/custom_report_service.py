import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.services.custom_report_generator import SECTION_NAMES, CustomReportGenerator
from app.models.custom_report_template import CustomReportTemplate
from app.services.audit_service import AuditService


class CustomReportService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _normalize_framework_filter(framework_filter: list[uuid.UUID] | None) -> list[str] | None:
        if framework_filter is None:
            return None
        return [str(item) for item in framework_filter]

    @staticmethod
    def _validate_sections(sections: list[str]) -> None:
        unknown = [section for section in sections if section not in SECTION_NAMES]
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown section(s): {', '.join(sorted(unknown))}",
            )

    def create_template(self, org_id: uuid.UUID, data, created_by: uuid.UUID) -> CustomReportTemplate:
        self._validate_sections(data.sections)
        row = CustomReportTemplate(
            organization_id=org_id,
            name=data.name,
            sections=data.sections,
            framework_filter=self._normalize_framework_filter(data.framework_filter),
            date_range_days=data.date_range_days,
            created_by=created_by,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="custom_report_template.created",
            entity_type="custom_report_template",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={
                "name": row.name,
                "sections": row.sections,
                "date_range_days": row.date_range_days,
            },
            metadata_json={"source": "api"},
        )
        return row

    def get_template(self, org_id: uuid.UUID, template_id: uuid.UUID) -> CustomReportTemplate:
        row = self.db.execute(
            select(CustomReportTemplate).where(
                CustomReportTemplate.organization_id == org_id,
                CustomReportTemplate.id == template_id,
                CustomReportTemplate.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Custom report template not found")
        return row

    def list_templates(self, org_id: uuid.UUID) -> list[CustomReportTemplate]:
        return self.db.execute(
            select(CustomReportTemplate)
            .where(
                CustomReportTemplate.organization_id == org_id,
                CustomReportTemplate.deleted_at.is_(None),
            )
            .order_by(CustomReportTemplate.created_at.desc())
        ).scalars().all()

    def update_template(self, org_id: uuid.UUID, template_id: uuid.UUID, data, user_id: uuid.UUID) -> CustomReportTemplate:
        row = self.get_template(org_id, template_id)
        before = {
            "name": row.name,
            "sections": row.sections,
            "framework_filter": row.framework_filter,
            "date_range_days": row.date_range_days,
        }

        if data.name is not None:
            row.name = data.name
        if data.sections is not None:
            self._validate_sections(data.sections)
            row.sections = data.sections
        if data.framework_filter is not None:
            row.framework_filter = self._normalize_framework_filter(data.framework_filter)
        if data.date_range_days is not None:
            row.date_range_days = data.date_range_days

        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="custom_report_template.updated",
            entity_type="custom_report_template",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            before_json=before,
            after_json={
                "name": row.name,
                "sections": row.sections,
                "framework_filter": row.framework_filter,
                "date_range_days": row.date_range_days,
            },
            metadata_json={"source": "api"},
        )
        return row

    def soft_delete_template(self, org_id: uuid.UUID, template_id: uuid.UUID, user_id: uuid.UUID) -> CustomReportTemplate:
        row = self.get_template(org_id, template_id)
        row.deleted_at = self._now()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="custom_report_template.deleted",
            entity_type="custom_report_template",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"deleted_at": row.deleted_at.isoformat()},
            metadata_json={"source": "api"},
        )
        return row

    def generate_from_template(self, org_id: uuid.UUID, template_id: uuid.UUID, db: Session, created_by: uuid.UUID):
        _ = db
        report = CustomReportGenerator(self.db).generate(
            template_id=template_id,
            org_id=org_id,
            db=self.db,
            created_by=created_by,
        )
        AuditService(self.db).write_audit_log(
            action="custom_report.generated",
            entity_type="compliance_report",
            entity_id=report.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={
                "report_type": report.report_type,
                "template_id": str(template_id),
                "title": report.title,
            },
            metadata_json={"source": "api"},
        )
        return report
