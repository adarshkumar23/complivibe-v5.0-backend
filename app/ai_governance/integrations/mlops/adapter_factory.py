import json
import uuid

from sqlalchemy.orm import Session

from app.ai_governance.integrations.mlops.mlflow_adapter import MLflowAdapter
from app.models.mlops_integration import MLOpsIntegration
from app.services.secrets_service import SecretsService, legacy_key_from_named_setting


def _secrets(db: Session, organization_id: uuid.UUID) -> SecretsService:
    return SecretsService(
        db,
        organization_id=organization_id,
        legacy_key_resolver=legacy_key_from_named_setting("MLOPS_CONFIG_ENCRYPTION_KEY"),
    )


def encrypt_config(
    config: dict, *, db: Session, organization_id: uuid.UUID, entity_id: uuid.UUID | None = None
) -> str:
    payload = json.dumps(config, sort_keys=True)
    return _secrets(db, organization_id).encrypt(payload, secret_name="mlops_integration_config", entity_id=entity_id)


def decrypt_config(
    config_json: str, *, db: Session, organization_id: uuid.UUID, entity_id: uuid.UUID | None = None
) -> dict:
    raw = _secrets(db, organization_id).decrypt(config_json, secret_name="mlops_integration_config", entity_id=entity_id)
    return json.loads(raw)


def get_adapter(integration: MLOpsIntegration, *, db: Session):
    """
    Decrypt config_json and return adapter.
    """
    from fastapi import HTTPException, status

    config = decrypt_config(
        integration.config_json, db=db, organization_id=integration.organization_id, entity_id=integration.id
    )
    if integration.integration_type == "mlflow":
        try:
            return MLflowAdapter(
                tracking_uri=str(config["tracking_uri"]),
                token=config.get("token"),
            )
        except ImportError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"MLflow integration unavailable: {exc}",
            ) from exc
    raise ValueError(f"Unsupported integration type: {integration.integration_type}")
