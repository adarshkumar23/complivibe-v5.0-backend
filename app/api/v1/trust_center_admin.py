import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.services.trust_center_service import TrustCenterService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.compliance_policy import CompliancePolicy
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.trust_center_access_request import TrustCenterAccessRequest
from app.models.trust_center_configuration import TrustCenterConfiguration
from app.models.trust_center_published_policy import TrustCenterPublishedPolicy
from app.models.user import User
from app.schemas.trust_center import (
    TrustCenterAccessRequestRead,
    TrustCenterAccessRequestReviewRequest,
    TrustCenterConfigurationRead,
    TrustCenterConfigurationUpsert,
    TrustCenterPublishPolicyRequest,
    TrustCenterPublishedPolicyRead,
    TrustCenterSetSlugRequest,
    TrustCenterSetSlugResponse,
    TrustCenterUptimeUpdateRequest,
)

router = APIRouter(prefix="/compliance/trust-center", tags=["trust-center-admin"])


def _config_read(row: TrustCenterConfiguration) -> TrustCenterConfigurationRead:
    return TrustCenterConfigurationRead(
        id=row.id,
        organization_id=row.organization_id,
        is_enabled=row.is_enabled,
        display_name=row.display_name,
        tagline=row.tagline,
        logo_url=row.logo_url,
        show_certifications=row.show_certifications,
        show_framework_coverage=row.show_framework_coverage,
        show_published_policies=row.show_published_policies,
        show_uptime_status=row.show_uptime_status,
        uptime_status=row.uptime_status,
        uptime_updated_at=row.uptime_updated_at,
        contact_email=row.contact_email,
        request_access_enabled=row.request_access_enabled,
        custom_message=row.custom_message,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _published_policy_read(db: Session, row: TrustCenterPublishedPolicy) -> TrustCenterPublishedPolicyRead:
    policy = db.execute(select(CompliancePolicy).where(CompliancePolicy.id == row.policy_id)).scalar_one_or_none()
    policy_title = policy.title if policy is not None else "Unknown policy"
    policy_archived = policy is None or policy.archived_at is not None or policy.status == "archived"
    policy_updated_since_published = policy is not None and policy.updated_at > row.published_at
    return TrustCenterPublishedPolicyRead(
        id=row.id,
        organization_id=row.organization_id,
        policy_id=row.policy_id,
        policy_title=policy_title,
        summary=row.summary,
        published_at=row.published_at,
        published_by=row.published_by,
        is_active=row.is_active,
        policy_archived=policy_archived,
        policy_updated_since_published=policy_updated_since_published,
        policy_last_updated_at=policy.updated_at if policy is not None else None,
    )


def _access_request_read(row: TrustCenterAccessRequest) -> TrustCenterAccessRequestRead:
    return TrustCenterAccessRequestRead(
        id=row.id,
        organization_id=row.organization_id,
        requester_name=row.requester_name,
        requester_email=row.requester_email,
        requester_company=row.requester_company,
        request_reason=row.request_reason,
        status=row.status,
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
        review_notes=row.review_notes,
        access_token_hash=row.access_token_hash,
        access_expires_at=row.access_expires_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/configuration", response_model=TrustCenterConfigurationRead)
def get_configuration(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> TrustCenterConfigurationRead:
    row = TrustCenterService(db).get_configuration(organization.id)
    return _config_read(row)


@router.post("/configuration", response_model=TrustCenterConfigurationRead)
def upsert_configuration(
    payload: TrustCenterConfigurationUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> TrustCenterConfigurationRead:
    row = TrustCenterService(db).create_or_update_configuration(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _config_read(row)


@router.post("/slug", response_model=TrustCenterSetSlugResponse)
def set_org_slug(
    payload: TrustCenterSetSlugRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> TrustCenterSetSlugResponse:
    row = TrustCenterService(db).set_org_slug(organization.id, payload.slug, current_user.id, confirm=payload.confirm)
    db.commit()
    db.refresh(row)
    return TrustCenterSetSlugResponse(organization_id=row.id, slug=row.slug or "")


@router.post("/publish-policy", response_model=TrustCenterPublishedPolicyRead)
def publish_policy(
    payload: TrustCenterPublishPolicyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> TrustCenterPublishedPolicyRead:
    row = TrustCenterService(db).publish_policy(organization.id, payload.policy_id, payload.summary, current_user.id)
    db.commit()
    db.refresh(row)
    return _published_policy_read(db, row)


@router.get("/policies", response_model=list[TrustCenterPublishedPolicyRead])
def list_published_policies(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> list[TrustCenterPublishedPolicyRead]:
    rows = TrustCenterService(db).list_published_policies(organization.id, include_inactive=include_inactive)
    return [TrustCenterPublishedPolicyRead(**row) for row in rows]


@router.delete("/policies/{policy_id}/unpublish", response_model=TrustCenterPublishedPolicyRead)
def unpublish_policy(
    policy_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> TrustCenterPublishedPolicyRead:
    row = TrustCenterService(db).unpublish_policy(organization.id, policy_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _published_policy_read(db, row)


@router.get("/access-requests", response_model=list[TrustCenterAccessRequestRead])
def list_access_requests(
    status_value: str | None = None,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor:read")),
) -> list[TrustCenterAccessRequestRead]:
    rows = TrustCenterService(db).list_access_requests(organization.id, status_value)
    db.commit()
    return [_access_request_read(row) for row in rows]


@router.post("/access-requests/{request_id}/review", response_model=TrustCenterAccessRequestRead)
def review_access_request(
    request_id: uuid.UUID,
    payload: TrustCenterAccessRequestReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> TrustCenterAccessRequestRead:
    row = TrustCenterService(db).review_access_request(
        organization.id,
        request_id,
        payload.action,
        current_user.id,
        notes=payload.notes,
    )
    db.commit()
    db.refresh(row)
    return _access_request_read(row)


@router.patch("/uptime-status", response_model=TrustCenterConfigurationRead)
def update_uptime_status(
    payload: TrustCenterUptimeUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:write")),
) -> TrustCenterConfigurationRead:
    row = TrustCenterService(db).update_uptime_status(organization.id, payload.status, current_user.id)
    db.commit()
    db.refresh(row)
    return _config_read(row)
