import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.governance_override_template import GovernanceOverrideTemplate
from app.models.governance_override_template_version import GovernanceOverrideTemplateVersion
from app.models.organization import Organization
from app.models.user import User
from app.repositories.governance_override_repository import GovernanceOverrideRepository
from app.schemas.governance_override import (
    GovernanceOverrideTemplateCreate,
    GovernanceOverrideTemplateDetail,
    GovernanceOverrideTemplateListResponse,
    GovernanceOverrideTemplateRead,
    GovernanceOverrideTemplateSummary,
    GovernanceOverrideTemplateUpdate,
    GovernanceOverrideTemplateVersionRead,
)
from app.services.audit_service import AuditService
from app.services.governance_override_service import GovernanceOverrideService

router = APIRouter(prefix="/governance/override-templates", tags=["governance-override-templates"])


def _template_read(row: GovernanceOverrideTemplate) -> GovernanceOverrideTemplateRead:
    return GovernanceOverrideTemplateRead(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        description=row.description,
        override_type=row.override_type,
        target_entity_type=row.target_entity_type,
        requested_action=row.requested_action,
        status=row.status,
        default_required_approvals=row.default_required_approvals,
        approver_role_names_json=row.approver_role_names_json,
        condition_rules_json=row.condition_rules_json,
        version=row.version,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _template_version_read(row: GovernanceOverrideTemplateVersion) -> GovernanceOverrideTemplateVersionRead:
    return GovernanceOverrideTemplateVersionRead(
        id=row.id,
        organization_id=row.organization_id,
        template_id=row.template_id,
        version=row.version,
        name=row.name,
        description=row.description,
        override_type=row.override_type,
        target_entity_type=row.target_entity_type,
        requested_action=row.requested_action,
        default_required_approvals=row.default_required_approvals,
        approver_role_names_json=row.approver_role_names_json,
        condition_rules_json=row.condition_rules_json,
        status=row.status,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
    )


@router.post("", response_model=GovernanceOverrideTemplateRead, status_code=status.HTTP_201_CREATED)
def create_template(
    payload: GovernanceOverrideTemplateCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("governance_override_template:write")),
) -> GovernanceOverrideTemplateRead:
    service = GovernanceOverrideService(db)
    row = service.create_template(
        organization_id=organization.id,
        name=payload.name,
        description=payload.description,
        override_type=payload.override_type,
        target_entity_type=payload.target_entity_type,
        requested_action=payload.requested_action,
        default_required_approvals=payload.default_required_approvals,
        approver_role_names_json=payload.approver_role_names_json,
        condition_rules_json=payload.condition_rules_json,
        status_value=payload.status,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="governance_override_template.created",
        entity_type="governance_override_template",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "name": row.name,
            "status": row.status,
            "version": row.version,
            "default_required_approvals": row.default_required_approvals,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _template_read(row)


@router.get("", response_model=GovernanceOverrideTemplateListResponse)
def list_templates(
    status_filter: str | None = Query(default=None, alias="status"),
    override_type: str | None = Query(default=None),
    target_entity_type: str | None = Query(default=None),
    requested_action: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("governance_override_template:read")),
) -> GovernanceOverrideTemplateListResponse:
    rows = GovernanceOverrideRepository(db).list_templates(
        organization_id=organization.id,
        status=status_filter,
        override_type=override_type,
        target_entity_type=target_entity_type,
        requested_action=requested_action,
        limit=limit,
        offset=offset,
    )
    return GovernanceOverrideTemplateListResponse(templates=[_template_read(row) for row in rows])


@router.get("/summary", response_model=GovernanceOverrideTemplateSummary)
def template_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("governance_override_template:read")),
) -> GovernanceOverrideTemplateSummary:
    return GovernanceOverrideTemplateSummary(**GovernanceOverrideService(db).template_summary(organization_id=organization.id))


@router.get("/{template_id}", response_model=GovernanceOverrideTemplateDetail)
def get_template_detail(
    template_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("governance_override_template:read")),
) -> GovernanceOverrideTemplateDetail:
    service = GovernanceOverrideService(db)
    row = service.require_template(organization_id=organization.id, template_id=template_id)
    versions = GovernanceOverrideRepository(db).list_template_versions(organization_id=organization.id, template_id=row.id)
    latest = versions[0] if versions else None
    return GovernanceOverrideTemplateDetail(
        template=_template_read(row),
        latest_version=_template_version_read(latest) if latest else None,
    )


@router.patch("/{template_id}", response_model=GovernanceOverrideTemplateRead)
def update_template(
    template_id: uuid.UUID,
    payload: GovernanceOverrideTemplateUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("governance_override_template:write")),
) -> GovernanceOverrideTemplateRead:
    service = GovernanceOverrideService(db)
    row = service.require_template(organization_id=organization.id, template_id=template_id)
    before = {
        "version": row.version,
        "status": row.status,
        "default_required_approvals": row.default_required_approvals,
    }
    row = service.update_template(
        template=row,
        actor_user_id=current_user.id,
        name=payload.name,
        description=payload.description,
        override_type=payload.override_type,
        target_entity_type=payload.target_entity_type,
        requested_action=payload.requested_action,
        default_required_approvals=payload.default_required_approvals,
        approver_role_names_json=payload.approver_role_names_json,
        condition_rules_json=payload.condition_rules_json,
        status_value=payload.status,
    )
    AuditService(db).write_audit_log(
        action="governance_override_template.updated",
        entity_type="governance_override_template",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "version": row.version,
            "status": row.status,
            "default_required_approvals": row.default_required_approvals,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _template_read(row)


@router.post("/{template_id}/archive", response_model=GovernanceOverrideTemplateRead)
def archive_template(
    template_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("governance_override_template:write")),
) -> GovernanceOverrideTemplateRead:
    service = GovernanceOverrideService(db)
    row = service.require_template(organization_id=organization.id, template_id=template_id)
    row = service.update_template(
        template=row,
        actor_user_id=current_user.id,
        name=None,
        description=None,
        override_type=None,
        target_entity_type=None,
        requested_action=None,
        default_required_approvals=None,
        approver_role_names_json=None,
        condition_rules_json=None,
        status_value="archived",
    )
    AuditService(db).write_audit_log(
        action="governance_override_template.archived",
        entity_type="governance_override_template",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"status": row.status, "version": row.version},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _template_read(row)


@router.get("/{template_id}/versions", response_model=list[GovernanceOverrideTemplateVersionRead])
def list_template_versions(
    template_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("governance_override_template:read")),
) -> list[GovernanceOverrideTemplateVersionRead]:
    service = GovernanceOverrideService(db)
    row = service.require_template(organization_id=organization.id, template_id=template_id)
    versions = GovernanceOverrideRepository(db).list_template_versions(organization_id=organization.id, template_id=row.id)
    return [_template_version_read(item) for item in versions]
