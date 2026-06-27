import base64
import hashlib
import json

from cryptography.fernet import Fernet

from app.ai_governance.integrations.mlops.mlflow_adapter import MLflowAdapter
from app.core.config import get_settings
from app.models.mlops_integration import MLOpsIntegration


def _fernet() -> Fernet:
    settings = get_settings()
    key_value = getattr(settings, "MLOPS_CONFIG_ENCRYPTION_KEY", None) or settings.SECRET_KEY
    digest = hashlib.sha256(key_value.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(digest)
    return Fernet(fernet_key)


def encrypt_config(config: dict) -> str:
    payload = json.dumps(config, sort_keys=True)
    return _fernet().encrypt(payload.encode("utf-8")).decode("utf-8")


def decrypt_config(config_json: str) -> dict:
    raw = _fernet().decrypt(config_json.encode("utf-8")).decode("utf-8")
    return json.loads(raw)


def get_adapter(integration: MLOpsIntegration):
    """
    Decrypt config_json and return adapter.
    """
    config = decrypt_config(integration.config_json)
    if integration.integration_type == "mlflow":
        return MLflowAdapter(
            tracking_uri=str(config["tracking_uri"]),
            token=config.get("token"),
        )
    raise ValueError(f"Unsupported integration type: {integration.integration_type}")
