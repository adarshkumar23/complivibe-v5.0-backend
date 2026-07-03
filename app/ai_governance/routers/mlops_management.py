from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.ai_governance.schemas.mlops_adapter import (
    MLflowComplianceStatusRequest,
    MLflowConnectionCreate,
    MLflowConnectionCreateResponse,
    MLflowConnectionRead,
    MLflowConnectionRotateResponse,
    MLflowDriftEventRead,
    MLflowManualLinkRequest,
    MLflowModelRegistrationRead,
)
from app.ai_governance.services.mlops_adapter_service import MLopsAdapterService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

org_router = APIRouter(prefix="/organizations", tags=["ai-governance-mlops"])
mlflow_router = APIRouter(prefix="/ai-governance/mlflow", tags=["ai-governance-mlops"])
coverage_router = APIRouter(prefix="/ai-governance", tags=["ai-governance-mlops"])


@org_router.get("/mlflow-connection", response_model=MLflowConnectionRead)
def get_mlflow_connection(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("integrations:read")),
) -> MLflowConnectionRead:
    service = MLopsAdapterService(db)
    row = service.get_connection(organization.id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MLflow connection not found")

    return MLflowConnectionRead(
        id=row.id,
        organization_id=row.organization_id,
        connection_name=row.connection_name,
        tracking_server_url=row.tracking_server_url,
        is_active=row.is_active,
        has_ingest_token=bool(row.ingest_token),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@org_router.post("/mlflow-connection", response_model=MLflowConnectionCreateResponse, status_code=status.HTTP_201_CREATED)
def create_mlflow_connection(
    payload: MLflowConnectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("integrations:write")),
) -> MLflowConnectionCreateResponse:
    row, token = MLopsAdapterService(db).create_connection(
        org_id=organization.id,
        connection_name=payload.connection_name,
        tracking_server_url=payload.tracking_server_url,
        created_by=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return MLflowConnectionCreateResponse(
        id=row.id,
        organization_id=row.organization_id,
        connection_name=row.connection_name,
        tracking_server_url=row.tracking_server_url,
        is_active=row.is_active,
        has_ingest_token=True,
        ingest_token=token,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@org_router.post("/mlflow-connection/rotate-token", response_model=MLflowConnectionRotateResponse)
def rotate_mlflow_connection_token(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("integrations:write")),
) -> MLflowConnectionRotateResponse:
    row, token = MLopsAdapterService(db).rotate_connection_token(org_id=organization.id, rotated_by=current_user.id)
    db.commit()
    return MLflowConnectionRotateResponse(id=row.id, ingest_token=token)


@org_router.delete("/mlflow-connection", response_model=MLflowConnectionRead)
def deactivate_mlflow_connection(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("integrations:write")),
) -> MLflowConnectionRead:
    row = MLopsAdapterService(db).deactivate_connection(org_id=organization.id, user_id=current_user.id)
    db.commit()
    db.refresh(row)
    return MLflowConnectionRead(
        id=row.id,
        organization_id=row.organization_id,
        connection_name=row.connection_name,
        tracking_server_url=row.tracking_server_url,
        is_active=row.is_active,
        has_ingest_token=bool(row.ingest_token),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@mlflow_router.get("/models", response_model=list[MLflowModelRegistrationRead])
def list_mlflow_model_registrations(
    ai_system_id: uuid.UUID | None = Query(default=None),
    compliance_status: str | None = Query(default=None),
    model_name: str | None = Query(default=None),
    stage: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("integrations:read")),
) -> list[MLflowModelRegistrationRead]:
    rows = MLopsAdapterService(db).list_model_registrations(
        org_id=organization.id,
        ai_system_id=ai_system_id,
        compliance_status=compliance_status,
        model_name=model_name,
        stage=stage,
        offset=offset,
        limit=limit,
    )
    return [MLflowModelRegistrationRead.model_validate(r) for r in rows]


@mlflow_router.post("/models/{registration_id}/link", response_model=MLflowModelRegistrationRead)
def manually_link_model_registration(
    registration_id: uuid.UUID,
    payload: MLflowManualLinkRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("integrations:write")),
) -> MLflowModelRegistrationRead:
    row = MLopsAdapterService(db).link_model_to_ai_system(
        org_id=organization.id,
        registration_id=registration_id,
        ai_system_id=payload.ai_system_id,
        linked_by=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return MLflowModelRegistrationRead.model_validate(row)


@mlflow_router.patch("/models/{registration_id}/compliance-status", response_model=MLflowModelRegistrationRead)
def update_mlflow_model_compliance_status(
    registration_id: uuid.UUID,
    payload: MLflowComplianceStatusRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("integrations:write")),
) -> MLflowModelRegistrationRead:
    row = MLopsAdapterService(db).update_compliance_status(
        org_id=organization.id,
        registration_id=registration_id,
        new_status=payload.status,
        updated_by=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return MLflowModelRegistrationRead.model_validate(row)


@mlflow_router.get("/drift", response_model=list[MLflowDriftEventRead])
def list_mlflow_drift_events(
    severity: str | None = Query(default=None),
    model_name: str | None = Query(default=None),
    ai_system_id: uuid.UUID | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("integrations:read")),
) -> list[MLflowDriftEventRead]:
    rows = MLopsAdapterService(db).list_drift_events(
        org_id=organization.id,
        severity=severity,
        model_name=model_name,
        ai_system_id=ai_system_id,
        offset=offset,
        limit=limit,
    )
    return [MLflowDriftEventRead.model_validate(r) for r in rows]


@coverage_router.get("/ai-systems/{ai_system_id}/mlops-coverage")
def get_mlops_coverage(
    ai_system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> dict:
    return MLopsAdapterService(db).get_mlops_coverage(org_id=organization.id, ai_system_id=ai_system_id)
