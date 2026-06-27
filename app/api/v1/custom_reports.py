import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.compliance.services.custom_report_service import CustomReportService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.custom_report_template import CustomReportTemplate
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.custom_reports import (
    CustomReportGenerateResponse,
    CustomReportTemplateCreate,
    CustomReportTemplateRead,
    CustomReportTemplateUpdate,
)

router = APIRouter(prefix="/compliance/custom-report-templates", tags=["custom-reports"])


def _template_read(row: CustomReportTemplate) -> CustomReportTemplateRead:
    return CustomReportTemplateRead(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        sections=list(row.sections or []),
        framework_filter=row.framework_filter,
        date_range_days=row.date_range_days,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
    )


@router.post("", response_model=CustomReportTemplateRead, status_code=status.HTTP_201_CREATED)
def create_custom_report_template(
    payload: CustomReportTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:write")),
) -> CustomReportTemplateRead:
    row = CustomReportService(db).create_template(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _template_read(row)


@router.get("", response_model=list[CustomReportTemplateRead])
def list_custom_report_templates(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:read")),
) -> list[CustomReportTemplateRead]:
    rows = CustomReportService(db).list_templates(organization.id)
    return [_template_read(row) for row in rows]


@router.get("/{template_id}", response_model=CustomReportTemplateRead)
def get_custom_report_template(
    template_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:read")),
) -> CustomReportTemplateRead:
    row = CustomReportService(db).get_template(organization.id, template_id)
    return _template_read(row)


@router.patch("/{template_id}", response_model=CustomReportTemplateRead)
def update_custom_report_template(
    template_id: uuid.UUID,
    payload: CustomReportTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:write")),
) -> CustomReportTemplateRead:
    row = CustomReportService(db).update_template(organization.id, template_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _template_read(row)


@router.delete("/{template_id}", response_model=CustomReportTemplateRead)
def delete_custom_report_template(
    template_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:write")),
) -> CustomReportTemplateRead:
    row = CustomReportService(db).soft_delete_template(organization.id, template_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _template_read(row)


@router.post("/{template_id}/generate", response_model=CustomReportGenerateResponse)
def generate_custom_report(
    template_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:read")),
) -> CustomReportGenerateResponse:
    report = CustomReportService(db).generate_from_template(organization.id, template_id, db, current_user.id)
    db.commit()
    db.refresh(report)
    return CustomReportGenerateResponse(report_id=report.id, report_type=report.report_type, title=report.title)
