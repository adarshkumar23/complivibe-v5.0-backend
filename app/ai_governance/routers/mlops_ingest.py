from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.ai_governance.schemas.mlops_adapter import MLflowIngestPayload
from app.ai_governance.services.mlops_adapter_service import MLopsAdapterService
from app.core.deps import get_db

router = APIRouter(prefix="/ingest", tags=["ai-governance-mlops"])


@router.post("/mlflow")
def ingest_mlflow_event(
    payload: MLflowIngestPayload,
    db: Session = Depends(get_db),
    x_mlflow_ingest_token: str | None = Header(default=None, alias="X-MLflow-Ingest-Token"),
) -> dict:
    if not x_mlflow_ingest_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing ingest token")

    service = MLopsAdapterService(db)
    connection = service.get_connection_by_token(x_mlflow_ingest_token)
    org_id = connection.organization_id

    event_type = payload.event_type.strip().lower()
    if event_type in {"model.registered", "model.deployed", "model.retired"}:
        if not payload.model_version:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="model_version is required")
        if not payload.stage:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="stage is required")

        service.ingest_model_event(
            connection_id=connection.id,
            org_id=org_id,
            event_type=event_type,
            model_name=payload.model_name,
            model_version=payload.model_version,
            ai_system_id=payload.ai_system_id,
            stage=payload.stage,
            run_id=payload.run_id,
            metrics_json=payload.metrics,
            tags_json=payload.tags,
            registered_at=payload.registered_at,
        )
    elif event_type == "drift.detected":
        if not payload.drift_metric:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="drift_metric is required")
        if payload.drift_value is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="drift_value is required")

        service.ingest_drift_event(
            connection_id=connection.id,
            org_id=org_id,
            model_name=payload.model_name,
            model_version=payload.model_version,
            ai_system_id=payload.ai_system_id,
            drift_metric=payload.drift_metric,
            drift_value=payload.drift_value,
            drift_threshold=payload.drift_threshold,
            drift_context_json=payload.drift_context,
            detected_at=payload.registered_at or datetime.now(UTC),
        )
    else:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported event_type")

    db.commit()
    return {"received": True}
