from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.schemas.scim import ScimPatchRequest, ScimTokenCreate, ScimTokenCreatedResponse, ScimTokenResponse
from app.auth.services.scim_auth import get_scim_organization
from app.auth.services.scim_service import SCIMService
from app.auth.services.scim_token_service import ScimTokenService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.core.billing_deps import require_feature
from app.core.rate_limiter import rate_limiter
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.role import Role
from app.models.scim_token import ScimToken
from app.models.user import User

router = APIRouter(tags=["auth-scim"])


class SCIMJSONResponse(JSONResponse):
    media_type = "application/scim+json"


def _scim_response(payload: dict, status_code: int = 200) -> SCIMJSONResponse:
    return SCIMJSONResponse(content=payload, status_code=status_code)


def _scim_error(status_code: int, detail: str) -> SCIMJSONResponse:
    return _scim_response(
        {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"],
            "status": str(status_code),
            "detail": detail,
        },
        status_code=status_code,
    )


def _require_admin_membership(db: Session, membership: Membership) -> None:
    role = db.execute(select(Role).where(Role.id == membership.role_id)).scalar_one_or_none()
    if role is None or role.name not in {"owner", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Org admin role required")


@router.get("/scim/v2/ServiceProviderConfig")
@rate_limiter.limiter.limit("60/minute")
def service_provider_config(request: Request) -> SCIMJSONResponse:
    return _scim_response(
        {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
            "documentationUri": "https://docs.complivibe.com",
            "patch": {"supported": True},
            "bulk": {"supported": False},
            "filter": {"supported": True, "maxResults": 200},
            "changePassword": {"supported": False},
            "sort": {"supported": False},
            "etag": {"supported": False},
            "authenticationSchemes": [
                {
                    "type": "oauthbearertoken",
                    "name": "OAuth Bearer Token",
                    "description": "Authentication using SCIM token",
                }
            ],
        }
    )


@router.get("/scim/v2/Schemas")
@rate_limiter.limiter.limit("60/minute")
def scim_schemas(request: Request) -> SCIMJSONResponse:
    return _scim_response(
        {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
            "totalResults": 1,
            "startIndex": 1,
            "itemsPerPage": 1,
            "Resources": [
                {
                    "id": "urn:ietf:params:scim:schemas:core:2.0:User",
                    "name": "User",
                    "description": "SCIM core User schema",
                    "attributes": [
                        {"name": "userName", "type": "string", "required": True},
                        {"name": "name.givenName", "type": "string", "required": False},
                        {"name": "name.familyName", "type": "string", "required": False},
                        {"name": "active", "type": "boolean", "required": False},
                    ],
                }
            ],
        }
    )


@router.get("/scim/v2/Users")
@rate_limiter.limiter.limit("60/minute")
def list_scim_users(
    request: Request,
    start_index: int = Query(default=1, alias="startIndex"),
    count: int = Query(default=100),
    filter_str: str | None = Query(default=None, alias="filter"),
    db: Session = Depends(get_db),
    org: Organization = Depends(get_scim_organization),
) -> SCIMJSONResponse:
    payload = SCIMService().list_users(org.id, start_index=start_index, count=count, filter_str=filter_str, db=db)
    db.commit()
    return _scim_response(payload)


@router.post("/scim/v2/Users")
@rate_limiter.limiter.limit("60/minute")
def create_scim_user(
    request: Request,
    payload: dict,
    db: Session = Depends(get_db),
    org: Organization = Depends(get_scim_organization),
) -> SCIMJSONResponse:
    email = str(payload.get("userName") or "").strip().lower()
    existing = None
    if email:
        existing = db.execute(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(
                Membership.organization_id == org.id,
                User.email == email,
            )
        ).scalar_one_or_none()
    row = SCIMService().provision_user(org.id, payload, db)
    db.commit()
    return _scim_response(row, status_code=200 if existing is not None else 201)


@router.get("/scim/v2/Users/{user_id}")
@rate_limiter.limiter.limit("60/minute")
def get_scim_user(
    request: Request,
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    org: Organization = Depends(get_scim_organization),
) -> SCIMJSONResponse:
    try:
        payload = SCIMService().get_user(org.id, user_id, db)
    except HTTPException as exc:
        db.rollback()
        return _scim_error(exc.status_code, str(exc.detail))
    db.commit()
    return _scim_response(payload)


@router.put("/scim/v2/Users/{user_id}")
@rate_limiter.limiter.limit("60/minute")
def put_scim_user(
    request: Request,
    user_id: uuid.UUID,
    payload: dict,
    db: Session = Depends(get_db),
    org: Organization = Depends(get_scim_organization),
) -> SCIMJSONResponse:
    try:
        body = SCIMService().update_user(org.id, user_id, payload, db)
    except HTTPException as exc:
        db.rollback()
        return _scim_error(exc.status_code, str(exc.detail))
    db.commit()
    return _scim_response(body)


@router.patch("/scim/v2/Users/{user_id}")
@rate_limiter.limiter.limit("60/minute")
def patch_scim_user(
    request: Request,
    user_id: uuid.UUID,
    payload: ScimPatchRequest,
    db: Session = Depends(get_db),
    org: Organization = Depends(get_scim_organization),
) -> SCIMJSONResponse:
    try:
        body = SCIMService().patch_user(
            org.id,
            user_id,
            operations=[item.model_dump() for item in payload.Operations],
            db=db,
        )
    except HTTPException as exc:
        db.rollback()
        return _scim_error(exc.status_code, str(exc.detail))
    db.commit()
    return _scim_response(body)


@router.delete("/scim/v2/Users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
@rate_limiter.limiter.limit("60/minute")
def delete_scim_user(
    request: Request,
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    org: Organization = Depends(get_scim_organization),
) -> Response:
    try:
        SCIMService().deprovision_user(org.id, user_id, db)
    except HTTPException as exc:
        db.rollback()
        return _scim_error(exc.status_code, str(exc.detail))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/scim-tokens",
    response_model=ScimTokenCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_feature("scim_enabled")],
)
def create_scim_token(
    payload: ScimTokenCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("org:update")),
) -> ScimTokenCreatedResponse:
    _require_admin_membership(db, membership)
    result = ScimTokenService().generate_token(
        org_id=organization.id,
        description=payload.description,
        created_by=current_user.id,
        expires_at=payload.expires_at,
        db=db,
    )
    token = db.get(ScimToken, uuid.UUID(result["token_id"]))
    db.commit()
    assert token is not None
    return ScimTokenCreatedResponse(
        id=token.id,
        description=token.description,
        is_active=token.is_active,
        created_at=token.created_at,
        last_used_at=token.last_used_at,
        expires_at=token.expires_at,
        raw_token=result["raw_token"],
        warning=result["warning"],
    )


@router.get("/scim-tokens", response_model=list[ScimTokenResponse])
def list_scim_tokens(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("org:read")),
) -> list[ScimTokenResponse]:
    _require_admin_membership(db, membership)
    rows = ScimTokenService().list_tokens(organization.id, db)
    return [ScimTokenResponse.model_validate(row) for row in rows]


@router.delete("/scim-tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scim_token(
    token_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("org:update")),
) -> Response:
    _require_admin_membership(db, membership)
    ScimTokenService().delete_token(organization.id, token_id, current_user.id, db)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
