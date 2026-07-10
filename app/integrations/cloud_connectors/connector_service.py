import secrets
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.validation import validate_choice
from app.models.cloud_evidence_connector import CONNECTOR_TYPES, CloudEvidenceConnector
from app.services.audit_service import AuditService
from app.services.secrets_service import SecretsService

SECRET_NAME = "cloud_evidence_connector_signing_secret"


class ConnectorHealthContext:
    """Staleness check, mirroring app.data_observability.services.quality_service's
    config_context shape: flag stale once no event has arrived in 2x the expected
    interval, and surface both a boolean and context_flags rather than a rigid enum."""

    @staticmethod
    def evaluate(connector: CloudEvidenceConnector, *, now: datetime | None = None) -> dict:
        evaluated_now = now or datetime.now(UTC)
        last_event_at = connector.last_event_received_at
        if last_event_at is not None and last_event_at.tzinfo is None:
            last_event_at = last_event_at.replace(tzinfo=UTC)

        hours_since_last_event: int | None = None
        is_stale = False
        if last_event_at is not None:
            hours_since_last_event = int((evaluated_now - last_event_at).total_seconds() // 3600)

        if connector.is_active and connector.status == "active":
            if last_event_at is None:
                is_stale = True
            elif hours_since_last_event is not None and hours_since_last_event > (connector.expected_event_interval_hours * 2):
                is_stale = True

        context_flags: list[str] = []
        if connector.is_active and last_event_at is None:
            context_flags.append("no_events_received_yet")
        if is_stale:
            context_flags.append("connector_stale")
        if connector.consecutive_error_count >= 3:
            context_flags.append("repeated_ingest_errors")

        return {
            "expected_event_interval_hours": connector.expected_event_interval_hours,
            "hours_since_last_event": hours_since_last_event,
            "is_stale": is_stale,
            "context_flags": context_flags,
        }


class CloudConnectorService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _require_connector(self, org_id: uuid.UUID, connector_id: uuid.UUID) -> CloudEvidenceConnector:
        row = self.db.execute(
            select(CloudEvidenceConnector).where(
                CloudEvidenceConnector.organization_id == org_id,
                CloudEvidenceConnector.id == connector_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")
        return row

    def get_by_webhook_token(self, connector_type: str, webhook_token: str) -> CloudEvidenceConnector:
        row = self.db.execute(
            select(CloudEvidenceConnector).where(
                CloudEvidenceConnector.connector_type == connector_type,
                CloudEvidenceConnector.webhook_token == webhook_token,
                CloudEvidenceConnector.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")
        return row

    def create_connector(
        self,
        org_id: uuid.UUID,
        connector_type: str,
        display_name: str,
        provider_config_json: dict | None,
        actor_user_id: uuid.UUID | None,
    ) -> tuple[CloudEvidenceConnector, str | None]:
        connector_type = validate_choice(connector_type, set(CONNECTOR_TYPES), "connector_type")
        webhook_token = secrets.token_urlsafe(32)
        connector_id = uuid.uuid4()

        # GCP authenticates via Google-signed OIDC bearer tokens, not a shared secret we mint.
        plaintext_secret: str | None = None
        signing_secret_ciphertext: str | None = None
        if connector_type != "gcp":
            plaintext_secret = secrets.token_urlsafe(32)
            signing_secret_ciphertext = SecretsService(self.db, organization_id=org_id, actor_user_id=actor_user_id).encrypt(
                plaintext_secret, secret_name=SECRET_NAME, entity_id=connector_id
            )

        now = self.utcnow()
        row = CloudEvidenceConnector(
            id=connector_id,
            organization_id=org_id,
            connector_type=connector_type,
            display_name=display_name,
            status="unconfigured",
            webhook_token=webhook_token,
            signing_secret_ciphertext=signing_secret_ciphertext,
            secret_revealed_at=now if plaintext_secret else None,
            provider_config_json=provider_config_json or {},
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="cloud_connector.created",
            entity_type="cloud_evidence_connector",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={"connector_type": connector_type, "display_name": display_name},
            metadata_json={"source": "api"},
        )
        return row, plaintext_secret

    def decrypt_signing_secret(self, connector: CloudEvidenceConnector) -> str | None:
        if connector.signing_secret_ciphertext is None:
            return None
        return SecretsService(self.db, organization_id=connector.organization_id).decrypt(
            connector.signing_secret_ciphertext, secret_name=SECRET_NAME, entity_id=connector.id
        )

    def activate_connector(self, org_id: uuid.UUID, connector_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> CloudEvidenceConnector:
        row = self._require_connector(org_id, connector_id)
        row.status = "active"
        row.updated_at = self.utcnow()
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="cloud_connector.activated",
            entity_type="cloud_evidence_connector",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={"status": "active"},
            metadata_json={"source": "api"},
        )
        return row

    def disable_connector(self, org_id: uuid.UUID, connector_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> CloudEvidenceConnector:
        row = self._require_connector(org_id, connector_id)
        row.status = "disabled"
        row.is_active = False
        row.updated_at = self.utcnow()
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="cloud_connector.disabled",
            entity_type="cloud_evidence_connector",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={"status": "disabled"},
            metadata_json={"source": "api"},
        )
        return row

    def list_connectors(self, org_id: uuid.UUID) -> list[CloudEvidenceConnector]:
        return self.db.execute(
            select(CloudEvidenceConnector).where(CloudEvidenceConnector.organization_id == org_id).order_by(CloudEvidenceConnector.created_at.desc())
        ).scalars().all()

    def get_connector(self, org_id: uuid.UUID, connector_id: uuid.UUID) -> CloudEvidenceConnector:
        return self._require_connector(org_id, connector_id)

    def record_event_received(self, connector: CloudEvidenceConnector, *, success: bool, error_message: str | None = None) -> None:
        connector.last_event_received_at = self.utcnow()
        if success:
            connector.consecutive_error_count = 0
            connector.last_error_message = None
            if connector.status == "unconfigured":
                connector.status = "active"
        else:
            connector.consecutive_error_count += 1
            connector.last_error_message = error_message
            if connector.consecutive_error_count >= 3:
                connector.status = "error"
        connector.updated_at = self.utcnow()
        self.db.flush()

    def health(self, org_id: uuid.UUID, connector_id: uuid.UUID) -> dict:
        connector = self._require_connector(org_id, connector_id)
        return ConnectorHealthContext.evaluate(connector)
