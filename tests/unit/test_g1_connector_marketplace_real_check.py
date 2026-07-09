"""Repro + regression coverage for G1 item 3: connector marketplace test-connection was fake
(schema-only, no real network call) and connector API tokens were stored in plaintext.
"""
import uuid

from sqlalchemy import select

from app.models.connector_catalog_entry import ConnectorOrgEnablement
from app.services.secrets_service import SecretsService


def _register(client, email, password="Pass1234!@", org_name="Org"):
    r = client.post("/api/v1/auth/register", json={"email": email, "password": password, "organization_name": org_name})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _headers(token, org_id=None):
    h = {"Authorization": f"Bearer {token}"}
    if org_id:
        h["X-Organization-ID"] = org_id
    return h


def _org_id(client, token):
    return client.get("/api/v1/organizations/me", headers=_headers(token)).json()[0]["id"]


def _create_connector_with_url_and_token(client, token, org_id):
    create = client.post(
        "/api/v1/connectors/catalog",
        headers=_headers(token, org_id),
        json={
            "name": "Repro API Connector",
            "category": "itsm",
            "description": "A connector with a network target and an api token field.",
            "config_schema": {
                "type": "object",
                "required": ["instance_url", "api_token"],
                "properties": {"instance_url": {"type": "string"}, "api_token": {"type": "string"}},
            },
        },
    )
    assert create.status_code == 201, create.text
    return create.json()["id"]


def test_repro_test_connection_reports_unreachable_target_honestly(client):
    token = _register(client, "g1-conn-a@example.com", org_name="G1 Conn Org A")
    org_id = _org_id(client, token)
    connector_id = _create_connector_with_url_and_token(client, token, org_id)

    # A guaranteed-fast-failing target: nothing listens on this local port, so this is a
    # deterministic "unreachable" case that doesn't depend on outbound internet access.
    enable = client.post(
        f"/api/v1/connectors/{connector_id}/enable",
        headers=_headers(token, org_id),
        json={"config_values_json": {"instance_url": "http://127.0.0.1:1", "api_token": "sk-repro-secret-value"}},
    )
    assert enable.status_code == 200, enable.text
    # Enabling only schema-validates; it must not falsely claim a verified live connection.
    assert enable.json()["connection_status"] == "validated"

    tested = client.post(f"/api/v1/connectors/{connector_id}/test-connection", headers=_headers(token, org_id))
    assert tested.status_code == 200, tested.text
    body = tested.json()
    # This is the crux of the repro: a genuinely fake/unreachable endpoint must NOT be reported
    # as "validated" once test-connection actually attempts a live call.
    assert body["connection_status"] == "unreachable", body
    assert body["connection_error"]


def test_repro_connector_api_token_encrypted_at_rest(client, db_session):
    token = _register(client, "g1-conn-b@example.com", org_name="G1 Conn Org B")
    org_id = _org_id(client, token)
    connector_id = _create_connector_with_url_and_token(client, token, org_id)

    secret_value = "sk-super-secret-plaintext-token-12345"
    enable = client.post(
        f"/api/v1/connectors/{connector_id}/enable",
        headers=_headers(token, org_id),
        json={"config_values_json": {"instance_url": "http://127.0.0.1:1", "api_token": secret_value}},
    )
    assert enable.status_code == 200, enable.text

    # The API response must never echo the plaintext token back.
    assert enable.json()["config_values_json"]["api_token"] != secret_value

    # The raw DB row must not contain the plaintext token either -- it must be vault ciphertext.
    row = db_session.execute(
        select(ConnectorOrgEnablement).where(ConnectorOrgEnablement.connector_id == uuid.UUID(connector_id))
    ).scalar_one()
    stored_token = row.config_values_json["api_token"]
    assert stored_token != secret_value
    assert SecretsService.is_vault_format(stored_token), stored_token

    # And it must decrypt back to the original value via the same vault-backed service used
    # elsewhere in the codebase (SecretsService), proving round-trip correctness.
    secrets = SecretsService(db_session, organization_id=uuid.UUID(org_id))
    assert secrets.decrypt(stored_token, secret_name="connector_config_value", entity_id=row.id) == secret_value

    # Non-sensitive fields (e.g. instance_url) are not encrypted -- only credential-shaped fields.
    assert row.config_values_json["instance_url"] == "http://127.0.0.1:1"
