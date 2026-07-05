import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import case, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.compliance.templates.esg_disclosure_templates import ESG_DISCLOSURE_TEMPLATES, ESG_TEMPLATE_TYPES
from app.compliance.services.custom_report_generator import SECTION_NAMES, CustomReportGenerator
from app.models.custom_report_template import CustomReportTemplate
from app.models.membership import Membership
from app.models.role import Role
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

    def _default_created_by_for_seed(self, org_id: uuid.UUID) -> uuid.UUID | None:
        # Prefer the earliest active owner/admin membership, then the earliest active
        # member. The user id tie-breaker keeps the seed actor deterministic.
        row = self.db.execute(
            select(Membership.user_id)
            .join(Role, Role.id == Membership.role_id)
            .where(
                Membership.organization_id == org_id,
                Membership.status == "active",
                Role.is_active.is_(True),
            )
            .order_by(
                case((Role.name == "owner", 0), (Role.name == "admin", 1), else_=2),
                Membership.created_at.asc(),
                Membership.user_id.asc(),
            )
            .limit(1)
        ).first()
        return row[0] if row else None

    def ensure_esg_templates(self, org_id: uuid.UUID) -> list[CustomReportTemplate]:
        created_by = self._default_created_by_for_seed(org_id)
        if created_by is None:
            return []

        rows: list[CustomReportTemplate] = []
        for template_type, payload in ESG_DISCLOSURE_TEMPLATES.items():
            row = self.db.execute(
                select(CustomReportTemplate).where(
                    CustomReportTemplate.organization_id == org_id,
                    CustomReportTemplate.system_template_key == payload["system_template_key"],
                    CustomReportTemplate.deleted_at.is_(None),
                )
            ).scalar_one_or_none()
            disclosure_structure = {
                "standard": payload["standard"],
                "sections": payload["sections"],
            }
            if row is None:
                candidate = CustomReportTemplate(
                    organization_id=org_id,
                    name=payload["name"],
                    template_type=template_type,
                    system_template_key=payload["system_template_key"],
                    sections=["esg_disclosure_template"],
                    disclosure_structure=disclosure_structure,
                    framework_filter=None,
                    date_range_days=365,
                    created_by=created_by,
                )
                try:
                    with self.db.begin_nested():
                        self.db.add(candidate)
                        self.db.flush()
                except IntegrityError:
                    # A concurrent request already seeded this template (the
                    # partial unique index on organization_id+system_template_key
                    # rejects the duplicate insert) — fetch the winner instead
                    # of surfacing a 500 for what is really a race, not an error.
                    row = self.db.execute(
                        select(CustomReportTemplate).where(
                            CustomReportTemplate.organization_id == org_id,
                            CustomReportTemplate.system_template_key == payload["system_template_key"],
                            CustomReportTemplate.deleted_at.is_(None),
                        )
                    ).scalar_one_or_none()
                    if row is None:
                        raise
                else:
                    row = candidate
                    AuditService(self.db).write_audit_log(
                        action="custom_report_template.seeded",
                        entity_type="custom_report_template",
                        entity_id=row.id,
                        organization_id=org_id,
                        actor_user_id=created_by,
                        after_json={
                            "name": row.name,
                            "template_type": row.template_type,
                            "system_template_key": row.system_template_key,
                        },
                        metadata_json={"source": "seed", "standard": payload["standard"]},
                    )
            else:
                before = {
                    "name": row.name,
                    "template_type": row.template_type,
                    "sections": row.sections,
                    "disclosure_structure": row.disclosure_structure,
                    "date_range_days": row.date_range_days,
                }
                after = {
                    "name": payload["name"],
                    "template_type": template_type,
                    "sections": ["esg_disclosure_template"],
                    "disclosure_structure": disclosure_structure,
                    "date_range_days": 365,
                }
                if before != after:
                    row.name = payload["name"]
                    row.template_type = template_type
                    row.sections = ["esg_disclosure_template"]
                    row.disclosure_structure = disclosure_structure
                    row.date_range_days = 365
                    self.db.flush()
                    AuditService(self.db).write_audit_log(
                        action="custom_report_template.seed_refreshed",
                        entity_type="custom_report_template",
                        entity_id=row.id,
                        organization_id=org_id,
                        actor_user_id=created_by,
                        before_json=before,
                        after_json=after,
                        metadata_json={"source": "seed", "standard": payload["standard"]},
                    )
            rows.append(row)
        return rows

    def create_template(self, org_id: uuid.UUID, data, created_by: uuid.UUID) -> CustomReportTemplate:
        self._validate_sections(data.sections)
        row = CustomReportTemplate(
            organization_id=org_id,
            name=data.name,
            template_type=data.template_type,
            sections=data.sections,
            disclosure_structure=data.disclosure_structure,
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
                "template_type": row.template_type,
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

    def list_templates(self, org_id: uuid.UUID, template_type: str | None = None) -> list[CustomReportTemplate]:
        self.ensure_esg_templates(org_id)
        stmt = select(CustomReportTemplate).where(
            CustomReportTemplate.organization_id == org_id,
            CustomReportTemplate.deleted_at.is_(None),
        )
        if template_type is not None:
            if template_type not in {"custom", *ESG_TEMPLATE_TYPES}:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown template_type")
            stmt = stmt.where(CustomReportTemplate.template_type == template_type)
        return self.db.execute(
            stmt.order_by(CustomReportTemplate.created_at.desc(), CustomReportTemplate.name.asc())
        ).scalars().all()

    def update_template(self, org_id: uuid.UUID, template_id: uuid.UUID, data, user_id: uuid.UUID) -> CustomReportTemplate:
        row = self.get_template(org_id, template_id)
        before = {
            "name": row.name,
            "template_type": row.template_type,
            "sections": row.sections,
            "disclosure_structure": row.disclosure_structure,
            "framework_filter": row.framework_filter,
            "date_range_days": row.date_range_days,
        }

        if data.name is not None:
            row.name = data.name
        if data.template_type is not None:
            if row.system_template_key:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Seeded template type cannot be changed")
            row.template_type = data.template_type
        if data.sections is not None:
            self._validate_sections(data.sections)
            row.sections = data.sections
        if data.disclosure_structure is not None:
            row.disclosure_structure = data.disclosure_structure
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
                "template_type": row.template_type,
                "sections": row.sections,
                "disclosure_structure": row.disclosure_structure,
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
