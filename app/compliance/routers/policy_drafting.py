from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.schemas.policy_drafting import (
    AICfgRead,
    AICfgUpdateRequest,
    PolicyDraftAcceptRequest,
    PolicyDraftCreateRequest,
    PolicyDraftCreateResponse,
    PolicyDraftListResponse,
    PolicyDraftRead,
)
from app.compliance.services.policy_drafting_service import PolicyDraftingService
from app.core.billing_deps import require_feature
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.role import Role
from app.models.user import User
from app.services.audit_service import AuditService

router = APIRouter(tags=["policy-drafting"])


def _require_org_admin(db: Session, membership: Membership) -> None:
    role = db.execute(select(Role).where(Role.id == membership.role_id)).scalar_one_or_none()
    if role is None or role.name not in {"owner", "admin"}:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Org admin role required")


def _draft_read(row) -> PolicyDraftRead:
    return PolicyDraftRead(
        id=row.id,
        organization_id=row.organization_id,
        business_unit_id=row.business_unit_id,
        content_type=row.content_type,
        prompt_input=row.prompt_input,
        draft_output=row.draft_output,
        provider_used=row.provider_used,
        used_byo_credentials=row.used_byo_credentials,
        status=row.status,
        linked_policy_id=row.linked_policy_id,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/compliance/policies/draft", response_model=PolicyDraftCreateResponse)
def create_policy_draft(
    payload: PolicyDraftCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:write")),
    __: Organization = require_feature("ai_policy_drafting"),
) -> PolicyDraftCreateResponse:
    row = PolicyDraftingService(db).create_policy_draft(
        org_id=organization.id,
        prompt_input=payload.prompt,
        business_unit_id=payload.business_unit_id,
        created_by=current_user.id,
    )

    AuditService(db).write_audit_log(
        action="ai_content.drafted",
        entity_type="ai_content_draft",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        metadata_json={"provider_used": row.provider_used, "used_byo_credentials": row.used_byo_credentials},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return PolicyDraftCreateResponse(
        id=row.id,
        draft_output=row.draft_output,
        provider_used=row.provider_used,
        used_byo_credentials=row.used_byo_credentials,
        status=row.status,
    )


@router.get("/compliance/policies/draft/{draft_id}", response_model=PolicyDraftRead)
def get_policy_draft(
    draft_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:read")),
    __: Organization = require_feature("ai_policy_drafting"),
) -> PolicyDraftRead:
    row = PolicyDraftingService(db).get_draft(organization.id, draft_id)
    return _draft_read(row)


@router.post("/compliance/policies/draft/{draft_id}/accept")
def accept_policy_draft(
    draft_id: uuid.UUID,
    payload: PolicyDraftAcceptRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:write")),
    __: Organization = require_feature("ai_policy_drafting"),
):
    row, policy_id = PolicyDraftingService(db).accept_draft(
        org_id=organization.id,
        draft_id=draft_id,
        title=payload.title,
        owner_user_id=payload.owner_user_id,
        description=payload.description,
        review_due_date=payload.review_due_date,
        effective_date=payload.effective_date,
        policy_type=payload.policy_type,
        accepted_by=current_user.id,
    )

    AuditService(db).write_audit_log(
        action="ai_content.accepted",
        entity_type="ai_content_draft",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        metadata_json={"linked_policy_id": str(policy_id)},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return {"draft_id": str(row.id), "status": row.status, "linked_policy_id": str(policy_id)}


@router.post("/compliance/policies/draft/{draft_id}/discard")
def discard_policy_draft(
    draft_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:write")),
    __: Organization = require_feature("ai_policy_drafting"),
):
    row = PolicyDraftingService(db).discard_draft(org_id=organization.id, draft_id=draft_id)

    AuditService(db).write_audit_log(
        action="ai_content.discarded",
        entity_type="ai_content_draft",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        metadata_json={"status": row.status},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return {"draft_id": str(row.id), "status": row.status}


@router.get("/compliance/policies/drafts", response_model=PolicyDraftListResponse)
def list_policy_drafts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    business_unit_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:read")),
    __: Organization = require_feature("ai_policy_drafting"),
) -> PolicyDraftListResponse:
    rows, total = PolicyDraftingService(db).list_drafts(
        org_id=organization.id,
        page=page,
        page_size=page_size,
        status_filter=status_filter,
        business_unit_id=business_unit_id,
    )
    return PolicyDraftListResponse(items=[_draft_read(row) for row in rows], total=total, page=page, page_size=page_size)


@router.get("/organizations/ai-configuration", response_model=AICfgRead)
def get_org_ai_configuration(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("compliance:read")),
) -> AICfgRead:
    _require_org_admin(db, membership)
    row = PolicyDraftingService(db).get_or_create_org_ai_config(organization.id)
    return AICfgRead(
        id=row.id,
        organization_id=row.organization_id,
        use_byo_credentials=row.use_byo_credentials,
        is_active=row.is_active,
        groq_api_key_configured=bool(row.groq_api_key_encrypted),
        azure_api_key_configured=bool(row.azure_api_key_encrypted),
        azure_endpoint=row.azure_endpoint,
        azure_deployment_name=row.azure_deployment_name,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.put("/organizations/ai-configuration", response_model=AICfgRead)
def put_org_ai_configuration(
    payload: AICfgUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("compliance:write")),
) -> AICfgRead:
    _require_org_admin(db, membership)
    row = PolicyDraftingService(db).update_org_ai_config(
        org_id=organization.id,
        use_byo_credentials=payload.use_byo_credentials,
        groq_api_key=payload.groq_api_key,
        azure_api_key=payload.azure_api_key,
        azure_endpoint=payload.azure_endpoint,
        azure_deployment_name=payload.azure_deployment_name,
        is_active=payload.is_active,
    )

    AuditService(db).write_audit_log(
        action="organization.ai_configuration_updated",
        entity_type="organization_ai_configuration",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        metadata_json={
            "use_byo_credentials": row.use_byo_credentials,
            "groq_api_key_configured": bool(row.groq_api_key_encrypted),
            "azure_api_key_configured": bool(row.azure_api_key_encrypted),
        },
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return AICfgRead(
        id=row.id,
        organization_id=row.organization_id,
        use_byo_credentials=row.use_byo_credentials,
        is_active=row.is_active,
        groq_api_key_configured=bool(row.groq_api_key_encrypted),
        azure_api_key_configured=bool(row.azure_api_key_encrypted),
        azure_endpoint=row.azure_endpoint,
        azure_deployment_name=row.azure_deployment_name,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
