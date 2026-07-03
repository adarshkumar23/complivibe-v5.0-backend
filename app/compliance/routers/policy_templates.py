import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.compliance.schemas.policy_template_library import (
    PolicyTemplateApplyRequest,
    PolicyTemplateApplyResponse,
    PolicyTemplateCreateRequest,
    PolicyTemplateResponse,
)
from app.compliance.services.policy_template_service import PolicyTemplateService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.policy_template import PolicyTemplate
from app.models.user import User
from app.schemas.policy_template import PolicyTemplateCloneRequest
from app.services.seed_service import SeedService

router = APIRouter(prefix="/compliance/policy-templates", tags=["policy-template-library"])


def _template_row_to_response(row: PolicyTemplate) -> PolicyTemplateResponse:
    return PolicyTemplateResponse(
        id=row.id,
        organization_id=row.organization_id,
        title=row.title or row.name,
        description=row.description,
        policy_type=row.policy_type,
        content=row.content,
        is_system=row.is_system,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _template_payload_for_legacy(row: dict[str, Any], model_row: PolicyTemplate | None) -> dict[str, Any]:
    payload = dict(row)
    payload["title"] = row.get("title") or row.get("name")
    payload["name"] = row.get("name") or row.get("title")
    payload["is_system"] = bool(row.get("is_system", False))
    payload["organization_id"] = row.get("organization_id")
    payload["policy_type"] = row.get("policy_type")
    if model_row is not None:
        payload["updated_at"] = model_row.updated_at
    return payload


@router.get("", response_model=list[dict[str, Any]])
def list_templates(
    category: str | None = Query(default=None),
    framework_tag: str | None = Query(default=None),
    search: str | None = Query(default=None),
    policy_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:read")),
) -> list[dict[str, Any]]:
    SeedService.ensure_policy_templates(db)
    rows = PolicyTemplateService(db).list_templates(
        org_id=organization.id,
        policy_type=policy_type,
        include_system=True,
        include_org_custom=True,
        page=page,
        page_size=page_size,
        category=category,
        framework_tag=framework_tag,
        search=search,
        is_active=True,
    )
    if not rows:
        return []
    template_ids = [row["id"] for row in rows]
    model_rows = db.query(PolicyTemplate).filter(PolicyTemplate.id.in_(template_ids)).all()
    by_id = {row.id: row for row in model_rows}
    return [_template_payload_for_legacy(row, by_id.get(row["id"])) for row in rows]


@router.get("/categories", response_model=list[dict[str, Any]])
def list_categories(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
    __: Organization = Depends(get_current_organization),
) -> list[dict[str, Any]]:
    SeedService.ensure_policy_templates(db)
    return PolicyTemplateService(db).list_categories()


@router.get("/frameworks", response_model=list[dict[str, Any]])
def list_frameworks(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
    __: Organization = Depends(get_current_organization),
) -> list[dict[str, Any]]:
    SeedService.ensure_policy_templates(db)
    return PolicyTemplateService(db).list_framework_tags()


@router.get("/clones", response_model=list[dict[str, Any]])
def list_clones(
    template_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:write")),
) -> list[dict[str, Any]]:
    rows = PolicyTemplateService(db).list_org_clones(organization.id, template_id=template_id)
    return [
        {
            "id": clone.id,
            "organization_id": clone.organization_id,
            "template_id": clone.template_id,
            "cloned_policy_id": clone.cloned_policy_id,
            "cloned_by": clone.cloned_by,
            "cloned_at": clone.cloned_at,
            "customization_notes": clone.customization_notes,
            "template": {
                "id": template.id,
                "slug": template.slug,
                "name": template.name,
                "category": template.category,
            },
            "policy": {
                "id": policy.id,
                "name": policy.title,
            },
        }
        for clone, template, policy in rows
    ]


@router.get("/slug/{slug}", response_model=dict[str, Any])
def get_template_by_slug(
    slug: str,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:read")),
) -> dict[str, Any]:
    SeedService.ensure_policy_templates(db)
    payload = PolicyTemplateService(db).get_template_by_slug(slug)
    row = db.query(PolicyTemplate).filter(PolicyTemplate.id == payload["id"]).first()
    if row is not None and row.organization_id is not None and row.organization_id != organization.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy template not found")
    return _template_payload_for_legacy(payload, row)


@router.get("/{template_id}/stats", response_model=dict[str, Any])
def get_template_stats(
    template_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
    __: Organization = Depends(get_current_organization),
    ___: Membership = Depends(require_permission("compliance_policies:write")),
) -> dict[str, Any]:
    return PolicyTemplateService(db).get_clone_stats(template_id)


@router.post("/{template_id}/clone", response_model=dict[str, Any], status_code=status.HTTP_201_CREATED)
def clone_template(
    template_id: uuid.UUID,
    payload: PolicyTemplateCloneRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:write")),
) -> dict[str, Any]:
    SeedService.ensure_policy_templates(db)
    clone, template, policy = PolicyTemplateService(db).clone_template(organization.id, template_id, payload, current_user.id)
    db.commit()
    db.refresh(clone)
    return {
        "id": clone.id,
        "organization_id": clone.organization_id,
        "template_id": clone.template_id,
        "cloned_policy_id": clone.cloned_policy_id,
        "cloned_by": clone.cloned_by,
        "cloned_at": clone.cloned_at,
        "customization_notes": clone.customization_notes,
        "template": {
            "id": template.id,
            "slug": template.slug,
            "name": template.name,
            "category": template.category,
        },
        "policy": {
            "id": policy.id,
            "name": policy.title,
        },
    }


@router.get("/{template_id}", response_model=dict[str, Any])
def get_template(
    template_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:read")),
) -> dict[str, Any]:
    row = PolicyTemplateService(db).get_template_for_org(template_id, organization.id)
    payload = PolicyTemplateService(db).get_template(row.id)
    return _template_payload_for_legacy(payload, row)


@router.post("/{template_id}/apply", response_model=PolicyTemplateApplyResponse)
def apply_template(
    template_id: uuid.UUID,
    payload: PolicyTemplateApplyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:write")),
) -> PolicyTemplateApplyResponse:
    row = PolicyTemplateService(db).apply_template(
        template_id=template_id,
        org_id=organization.id,
        applied_by=current_user.id,
        override_title=payload.override_title,
    )
    db.commit()
    db.refresh(row)
    return PolicyTemplateApplyResponse(policy_id=row.id, title=row.title, status=row.status)


@router.post("", response_model=PolicyTemplateResponse, status_code=status.HTTP_201_CREATED)
def create_org_template(
    payload: PolicyTemplateCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:write")),
) -> PolicyTemplateResponse:
    row = PolicyTemplateService(db).create_org_template(
        org_id=organization.id,
        title=payload.title,
        description=payload.description,
        policy_type=payload.policy_type,
        content=payload.content,
        created_by=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _template_row_to_response(row)
