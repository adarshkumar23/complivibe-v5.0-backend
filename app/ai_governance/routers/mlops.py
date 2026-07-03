import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.ai_governance.schemas.mlops import (
    MLOpsIntegrationCreate,
    MLOpsIntegrationRead,
    MLOpsIntegrationUpdate,
    MLOpsSyncLogRead,
    MLOpsSyncResult,
)
from app.ai_governance.services.mlops_sync_service import MLOPSSyncService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/ai-governance/mlops-integrations", tags=["ai-governance-mlops"])


@router.post("", response_model=MLOpsIntegrationRead, status_code=status.HTTP_201_CREATED)
def create_mlops_integration(
    payload: MLOpsIntegrationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("integrations:write")),
) -> MLOpsIntegrationRead:
    row = MLOPSSyncService(db).create_integration(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return MLOpsIntegrationRead.model_validate(row)


@router.get("", response_model=list[MLOpsIntegrationRead])
def list_mlops_integrations(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("integrations:read")),
) -> list[MLOpsIntegrationRead]:
    rows = MLOPSSyncService(db).list_integrations(organization.id)
    return [MLOpsIntegrationRead.model_validate(row) for row in rows]


@router.get("/{integration_id}", response_model=MLOpsIntegrationRead)
def get_mlops_integration(
    integration_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("integrations:read")),
) -> MLOpsIntegrationRead:
    row = MLOPSSyncService(db).get_integration(organization.id, integration_id)
    return MLOpsIntegrationRead.model_validate(row)


@router.patch("/{integration_id}", response_model=MLOpsIntegrationRead)
def update_mlops_integration(
    integration_id: uuid.UUID,
    payload: MLOpsIntegrationUpdate,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("integrations:write")),
) -> MLOpsIntegrationRead:
    row = MLOPSSyncService(db).update_integration(organization.id, integration_id, payload)
    db.commit()
    db.refresh(row)
    return MLOpsIntegrationRead.model_validate(row)


@router.post("/{integration_id}/deactivate", response_model=MLOpsIntegrationRead)
def deactivate_mlops_integration(
    integration_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("integrations:write")),
) -> MLOpsIntegrationRead:
    row = MLOPSSyncService(db).deactivate_integration(organization.id, integration_id, current_user.id)
    db.commit()
    db.refresh(row)
    return MLOpsIntegrationRead.model_validate(row)


@router.post("/{integration_id}/sync", response_model=MLOpsSyncResult)
def sync_mlops_integration(
    integration_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("integrations:write")),
) -> MLOpsSyncResult:
    try:
        result = MLOPSSyncService(db).sync(organization.id, integration_id, current_user.id)
        db.commit()
        return MLOpsSyncResult(**result)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"MLOps sync failed: {exc}",
        ) from exc


@router.get("/{integration_id}/sync-log", response_model=MLOpsSyncLogRead)
def get_mlops_sync_log(
    integration_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("integrations:read")),
) -> MLOpsSyncLogRead:
    row = MLOPSSyncService(db).get_sync_log(organization.id, integration_id)
    return MLOpsSyncLogRead(
        id=row.id,
        sync_status=row.sync_status,
        last_synced_at=row.last_synced_at,
        last_sync_error=row.last_sync_error,
    )
