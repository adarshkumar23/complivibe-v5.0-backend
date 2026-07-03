import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.schemas.sso import (
    SSOCallbackResponse,
    SSOConfigCreate,
    SSOConfigResponse,
    SSOConfigUpdate,
    SSOInitiateResponse,
    SSOTestConfigResponse,
)
from app.auth.services.sso_config_service import SSOConfigService
from app.auth.services.sso_service import SSOService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.core.billing_deps import require_feature
from app.core.rate_limiter import rate_limiter
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.role import Role
from app.models.user import User

router = APIRouter(tags=["auth-sso"])


def _require_admin_membership(db: Session, membership: Membership) -> None:
    role = db.execute(select(Role).where(Role.id == membership.role_id)).scalar_one_or_none()
    if role is None or role.name not in {"owner", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Org admin role required")


@router.get("/auth/sso/{org_slug}/metadata")
@rate_limiter.limiter.limit("120/minute")
def get_sso_metadata(org_slug: str, request: Request, db: Session = Depends(get_db)) -> Response:
    xml_payload = SSOService().get_sp_metadata(org_slug=org_slug, db=db)
    return Response(content=xml_payload, media_type="application/xml")


@router.post("/auth/sso/{org_slug}/initiate", response_model=SSOInitiateResponse)
@rate_limiter.limiter.limit("10/minute")
def initiate_sso(org_slug: str, request: Request, db: Session = Depends(get_db)) -> SSOInitiateResponse:
    redirect_url = SSOService().initiate_login(org_slug=org_slug, db=db)
    return SSOInitiateResponse(redirect_url=redirect_url)


@router.post("/auth/sso/{org_slug}/callback", response_model=SSOCallbackResponse)
@rate_limiter.limiter.limit("10/minute")
def sso_callback(
    org_slug: str,
    request: Request,
    saml_response: Annotated[str, Form(alias="SAMLResponse")],
    db: Session = Depends(get_db),
) -> SSOCallbackResponse:
    payload = SSOService().process_callback(org_slug=org_slug, saml_response=saml_response, db=db)
    db.commit()
    return SSOCallbackResponse(**payload)


@router.post(
    "/sso-configs",
    response_model=SSOConfigResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_feature("sso_enabled")],
)
def create_sso_config(
    payload: SSOConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("org:update")),
) -> SSOConfigResponse:
    _require_admin_membership(db, membership)
    row = SSOConfigService(db).create_config(organization.id, payload, current_user.id, db)
    db.commit()
    db.refresh(row)
    return SSOConfigResponse.model_validate(row)


@router.get("/sso-configs", response_model=SSOConfigResponse)
def get_sso_config(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("org:read")),
) -> SSOConfigResponse:
    _require_admin_membership(db, membership)
    row = SSOConfigService(db).get_config(organization.id, db)
    return SSOConfigResponse.model_validate(row)


@router.patch("/sso-configs/{config_id}", response_model=SSOConfigResponse)
def update_sso_config(
    config_id: uuid.UUID,
    payload: SSOConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("org:update")),
) -> SSOConfigResponse:
    _require_admin_membership(db, membership)
    row = SSOConfigService(db).update_config(organization.id, config_id, payload, current_user.id, db)
    db.commit()
    db.refresh(row)
    return SSOConfigResponse.model_validate(row)


@router.post("/sso-configs/{config_id}/activate", response_model=SSOConfigResponse)
def activate_sso_config(
    config_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("org:update")),
) -> SSOConfigResponse:
    _require_admin_membership(db, membership)
    row = SSOConfigService(db).activate_config(organization.id, config_id, current_user.id, db)
    db.commit()
    db.refresh(row)
    return SSOConfigResponse.model_validate(row)


@router.post("/sso-configs/{config_id}/deactivate", response_model=SSOConfigResponse)
def deactivate_sso_config(
    config_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("org:update")),
) -> SSOConfigResponse:
    _require_admin_membership(db, membership)
    row = SSOConfigService(db).deactivate_config(organization.id, config_id, current_user.id, db)
    db.commit()
    db.refresh(row)
    return SSOConfigResponse.model_validate(row)


@router.delete("/sso-configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sso_config(
    config_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("org:update")),
) -> Response:
    _require_admin_membership(db, membership)
    SSOConfigService(db).soft_delete_config(organization.id, config_id, current_user.id, db)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sso-configs/{config_id}/test", response_model=SSOTestConfigResponse)
def test_sso_config(
    config_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("org:read")),
) -> SSOTestConfigResponse:
    _require_admin_membership(db, membership)
    valid, errors = SSOConfigService(db).test_config(organization.id, config_id, db)
    return SSOTestConfigResponse(valid=valid, errors=errors)
