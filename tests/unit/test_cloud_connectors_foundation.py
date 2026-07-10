from __future__ import annotations

import uuid

from app.integrations.cloud_connectors.connector_service import CloudConnectorService
from app.models.cloud_evidence_connector import CloudEvidenceConnector
from app.services.secrets_service import SecretsService
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/cloud-connectors"


def test_create_connector_encrypts_secret_at_rest_and_reveals_once(client, db_session):
    org = bootstrap_org_user(client, email_prefix="cloud-connector-aws")

    create = client.post(
        BASE,
        headers=org["org_headers"],
        json={"connector_type": "aws", "display_name": "AWS Security Hub"},
    )
    assert create.status_code == 201
    body = create.json()
    assert body["signing_secret"] is not None
    connector_id = body["connector"]["id"]

    row = db_session.get(CloudEvidenceConnector, uuid.UUID(connector_id))
    assert row is not None
    assert row.signing_secret_ciphertext is not None
    assert SecretsService.is_vault_format(row.signing_secret_ciphertext)
    assert row.signing_secret_ciphertext != body["signing_secret"]

    decrypted = CloudConnectorService(db_session).decrypt_signing_secret(row)
    assert decrypted == body["signing_secret"]

    setup = client.get(f"{BASE}/{connector_id}/setup", headers=org["org_headers"])
    assert setup.status_code == 200
    assert setup.json()["signing_secret"] is None  # never re-shown after creation
    assert setup.json()["webhook_url"].endswith(f"/aws/{row.webhook_token}")


def test_gcp_connector_has_no_signing_secret(client):
    org = bootstrap_org_user(client, email_prefix="cloud-connector-gcp")
    create = client.post(
        BASE,
        headers=org["org_headers"],
        json={"connector_type": "gcp", "display_name": "GCP SCC", "provider_config_json": {"service_account_email": "svc@proj.iam.gserviceaccount.com"}},
    )
    assert create.status_code == 201
    assert create.json()["signing_secret"] is None


def test_connector_health_stale_when_no_events_received(client, db_session):
    org = bootstrap_org_user(client, email_prefix="cloud-connector-health")
    create = client.post(
        BASE,
        headers=org["org_headers"],
        json={"connector_type": "github", "display_name": "GitHub"},
    )
    connector_id = create.json()["connector"]["id"]

    health = client.get(f"{BASE}/{connector_id}/health", headers=org["org_headers"])
    assert health.status_code == 200
    body = health.json()
    assert body["hours_since_last_event"] is None
    # Not yet activated (status="unconfigured"), so not flagged stale until it goes active.
    assert body["is_stale"] is False

    CloudConnectorService(db_session).activate_connector(uuid.UUID(org["organization_id"]), uuid.UUID(connector_id), None)
    db_session.commit()

    health2 = client.get(f"{BASE}/{connector_id}/health", headers=org["org_headers"])
    assert health2.json()["is_stale"] is True
    assert "no_events_received_yet" in health2.json()["context_flags"]


def test_disable_connector_deactivates(client):
    org = bootstrap_org_user(client, email_prefix="cloud-connector-disable")
    create = client.post(
        BASE,
        headers=org["org_headers"],
        json={"connector_type": "okta", "display_name": "Okta"},
    )
    connector_id = create.json()["connector"]["id"]

    disable = client.post(f"{BASE}/{connector_id}/disable", headers=org["org_headers"])
    assert disable.status_code == 200
    assert disable.json()["status"] == "disabled"
    assert disable.json()["is_active"] is False
