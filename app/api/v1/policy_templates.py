import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.compliance.services.policy_template_service import PolicyTemplateService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.policy_template import PolicyTemplate
from app.models.policy_template_clone import PolicyTemplateClone
from app.models.user import User
from app.schemas.policy_template import (
    PolicySummary,
    PolicyTemplateCloneRequest,
    PolicyTemplateCloneResponse,
    PolicyTemplateDetailResponse,
    PolicyTemplateListResponse,
    PolicyTemplateStatsResponse,
    PolicyTemplateSummary,
    TemplateCategoryCountResponse,
    TemplateFrameworkCountResponse,
)
from app.services.seed_service import SeedService

router = APIRouter(prefix="/compliance", tags=["policy-templates"])


def _template_list_read(payload: dict) -> PolicyTemplateListResponse:
    return PolicyTemplateListResponse(
        id=payload["id"],
        slug=payload["slug"],
        name=payload["name"],
        description=payload["description"],
        category=payload["category"],
        framework_tags=payload["framework_tags"],
        version=payload["version"],
        is_active=payload["is_active"],
        created_at=payload["created_at"],
        clone_count=payload["clone_count"],
    )


def _template_detail_read(payload: dict) -> PolicyTemplateDetailResponse:
    base = _template_list_read(payload)
    return PolicyTemplateDetailResponse(**base.model_dump(), content=payload["content"])


def _clone_read(row: PolicyTemplateClone, template: PolicyTemplate, policy_name: str) -> PolicyTemplateCloneResponse:
    return PolicyTemplateCloneResponse(
        id=row.id,
        organization_id=row.organization_id,
        template_id=row.template_id,
        cloned_policy_id=row.cloned_policy_id,
        cloned_by=row.cloned_by,
        cloned_at=row.cloned_at,
        customization_notes=row.customization_notes,
        template=PolicyTemplateSummary(
            id=template.id,
            slug=template.slug,
            name=template.name,
            category=template.category,
        ),
        policy=PolicySummary(id=row.cloned_policy_id, name=policy_name),
    )


@router.get("/policy-templates", response_model=list[PolicyTemplateListResponse])
def list_policy_templates(
    category: str | None = Query(default=None),
    framework_tag: str | None = Query(default=None),
    search: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> list[PolicyTemplateListResponse]:
    _ = current_user
    _ = organization
    SeedService.ensure_policy_templates(db)
    rows = PolicyTemplateService(db).list_templates(category=category, framework_tag=framework_tag, search=search, is_active=True)
    return [_template_list_read(row) for row in rows]


@router.get("/policy-templates/categories", response_model=list[TemplateCategoryCountResponse])
def list_policy_template_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> list[TemplateCategoryCountResponse]:
    _ = current_user
    _ = organization
    SeedService.ensure_policy_templates(db)
    rows = PolicyTemplateService(db).list_categories()
    return [TemplateCategoryCountResponse(**row) for row in rows]


@router.get("/policy-templates/frameworks", response_model=list[TemplateFrameworkCountResponse])
def list_policy_template_frameworks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> list[TemplateFrameworkCountResponse]:
    _ = current_user
    _ = organization
    SeedService.ensure_policy_templates(db)
    rows = PolicyTemplateService(db).list_framework_tags()
    return [TemplateFrameworkCountResponse(**row) for row in rows]


@router.get("/policy-templates/clones", response_model=list[PolicyTemplateCloneResponse])
def list_policy_template_clones(
    template_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:write")),
) -> list[PolicyTemplateCloneResponse]:
    _ = current_user
    rows = PolicyTemplateService(db).list_org_clones(organization.id, template_id=template_id)
    return [_clone_read(clone, template, policy.title) for clone, template, policy in rows]


@router.get("/policy-templates/slug/{slug}", response_model=PolicyTemplateDetailResponse)
def get_policy_template_by_slug(
    slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> PolicyTemplateDetailResponse:
    _ = current_user
    _ = organization
    SeedService.ensure_policy_templates(db)
    payload = PolicyTemplateService(db).get_template_by_slug(slug)
    return _template_detail_read(payload)


@router.get("/policy-templates/{template_id}/stats", response_model=PolicyTemplateStatsResponse)
def get_policy_template_stats(
    template_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:write")),
) -> PolicyTemplateStatsResponse:
    _ = current_user
    _ = organization
    payload = PolicyTemplateService(db).get_clone_stats(template_id)
    return PolicyTemplateStatsResponse(**payload)


@router.post(
    "/policy-templates/{template_id}/clone",
    response_model=PolicyTemplateCloneResponse,
    status_code=status.HTTP_201_CREATED,
)
def clone_policy_template(
    template_id: uuid.UUID,
    payload: PolicyTemplateCloneRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:write")),
) -> PolicyTemplateCloneResponse:
    SeedService.ensure_policy_templates(db)
    clone, template, policy = PolicyTemplateService(db).clone_template(organization.id, template_id, payload, current_user.id)
    db.commit()
    db.refresh(clone)
    return _clone_read(clone, template, policy.title)


@router.get("/policy-templates/{template_id}", response_model=PolicyTemplateDetailResponse)
def get_policy_template(
    template_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> PolicyTemplateDetailResponse:
    _ = current_user
    _ = organization
    SeedService.ensure_policy_templates(db)
    payload = PolicyTemplateService(db).get_template(template_id)
    return _template_detail_read(payload)
