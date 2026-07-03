from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.integrations.security.schemas import FidesImportResponse, FidesImportStatusResponse
from app.integrations.security.services.fides_import_service import FidesImportService
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/privacy/import/fides", tags=["privacy-fides-import"])


@router.post("", response_model=FidesImportResponse)
def import_fides_manifest(
    payload: Any = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> FidesImportResponse:
    summary = FidesImportService().import_manifest(
        org_id=organization.id,
        payload=payload,
        imported_by=current_user.id,
        db=db,
    )
    db.commit()
    return FidesImportResponse(**summary)


@router.get("/status", response_model=FidesImportStatusResponse)
def get_fides_import_status(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> FidesImportStatusResponse:
    payload = FidesImportService().get_import_status(org_id=organization.id, db=db)
    return FidesImportStatusResponse(**payload)
