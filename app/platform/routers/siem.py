from __future__ import annotations

from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.core.billing_deps import require_feature
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.role import Role
from app.models.siem_export_run import SiemExportRun
from app.models.user import User
from app.platform.schemas.siem import (
    SiemConfigCreate,
    SiemConfigResponse,
    SiemConfigUpdate,
    SiemExportRequest,
    SiemExportResponse,
)
from app.platform.services.siem_export_service import SiemExportService

router = APIRouter(prefix="/siem", tags=["siem"])


class SiemExportRunResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    config_id: uuid.UUID
    status: str
    records_exported: int
    started_at: datetime
    completed_at: datetime | None
    error_message: str | None
    cursor_start: uuid.UUID | None
    cursor_end: uuid.UUID | None


def _require_admin_membership(db: Session, membership: Membership) -> None:
    role = db.execute(select(Role).where(Role.id == membership.role_id)).scalar_one_or_none()
    if role is None or role.name not in {"owner", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Org admin role required")


def _run_to_response(row: SiemExportRun) -> SiemExportRunResponse:
    return SiemExportRunResponse(
        id=row.id,
        organization_id=row.organization_id,
        config_id=row.config_id,
        status=row.status,
        records_exported=row.records_exported,
        started_at=row.started_at,
        completed_at=row.completed_at,
        error_message=row.error_message,
        cursor_start=row.cursor_start,
        cursor_end=row.cursor_end,
    )


@router.post(
    "/config",
    response_model=SiemConfigResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_feature("siem_export")],
)
def create_config(
    payload: SiemConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("org:update")),
) -> SiemConfigResponse:
    _require_admin_membership(db, membership)
    row = SiemExportService().create_config(organization.id, payload, current_user.id, db)
    db.commit()
    db.refresh(row)
    return SiemConfigResponse.model_validate(row)


@router.get("/config", response_model=SiemConfigResponse)
def get_config(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("org:read")),
) -> SiemConfigResponse:
    _require_admin_membership(db, membership)
    row = SiemExportService().get_config(organization.id, db)
    return SiemConfigResponse.model_validate(row)


@router.patch("/config", response_model=SiemConfigResponse)
def patch_config(
    payload: SiemConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("org:update")),
) -> SiemConfigResponse:
    _require_admin_membership(db, membership)
    row = SiemExportService().update_config(organization.id, payload, current_user.id, db)
    db.commit()
    db.refresh(row)
    return SiemConfigResponse.model_validate(row)


@router.post("/config/activate", response_model=SiemConfigResponse)
def activate_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("org:update")),
) -> SiemConfigResponse:
    _require_admin_membership(db, membership)
    row = SiemExportService().activate_config(organization.id, current_user.id, db)
    db.commit()
    db.refresh(row)
    return SiemConfigResponse.model_validate(row)


@router.post("/config/deactivate", response_model=SiemConfigResponse)
def deactivate_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("org:update")),
) -> SiemConfigResponse:
    _require_admin_membership(db, membership)
    row = SiemExportService().deactivate_config(organization.id, current_user.id, db)
    db.commit()
    db.refresh(row)
    return SiemConfigResponse.model_validate(row)


@router.delete("/config", status_code=status.HTTP_204_NO_CONTENT)
def delete_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("org:update")),
) -> Response:
    _require_admin_membership(db, membership)
    SiemExportService().delete_config(organization.id, current_user.id, db)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/export", response_model=SiemExportResponse)
def export_batch(
    payload: SiemExportRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:read")),
) -> SiemExportResponse:
    result = SiemExportService().export_batch(
        org_id=organization.id,
        db=db,
        limit=payload.limit,
        since_id=payload.since_id,
    )
    db.commit()
    return SiemExportResponse.model_validate(result)


@router.get("/export/runs", response_model=list[SiemExportRunResponse])
def list_export_runs(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:read")),
) -> list[SiemExportRunResponse]:
    rows = SiemExportService().list_runs(organization.id, db)
    return [_run_to_response(row) for row in rows]


@router.get("/export/preview", response_model=SiemExportResponse)
def preview_export(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:read")),
) -> SiemExportResponse:
    result = SiemExportService().preview_export(organization.id, db)
    return SiemExportResponse.model_validate(result)
