import uuid

from app.models.audit_log import AuditLog


def _register(client, email: str, password: str, org_name: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "organization_name": org_name},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str, org_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organization-ID"] = org_id
    return headers


def _org_id(client, token: str) -> str:
    return client.get("/api/v1/organizations/me", headers=_headers(token)).json()[0]["id"]


def test_t34_connector_catalog_crud_enable_disable_and_audit(client, db_session):
    token = _register(client, "t34-owner1@example.com", "Pass1234!@", "T34 Connector Org1")
    org_id = _org_id(client, token)

    create = client.post(
        "/api/v1/connectors/catalog",
        headers=_headers(token, org_id),
        json={
            "name": "Generic emissions import",
            "category": "sustainability",
            "description": "Uploads periodic emissions readings from a controlled file source.",
            "config_schema": {
                "type": "object",
                "required": ["file_format"],
                "properties": {"file_format": {"type": "string"}, "scope_mapping": {"type": "object"}},
            },
        },
    )
    assert create.status_code == 201, create.text
    connector = create.json()
    connector_id = connector["id"]
    assert connector["enabled"] is True
    assert "arelle" not in str(connector).lower()

    listed = client.get("/api/v1/connectors/catalog?category=sustainability", headers=_headers(token, org_id))
    assert listed.status_code == 200
    assert any(item["id"] == connector_id for item in listed.json())

    enabled = client.post(
        f"/api/v1/connectors/{connector_id}/enable",
        headers=_headers(token, org_id),
        json={"config_values_json": {"file_format": "csv", "scope_mapping": {"scope_1": "scope1"}}},
    )
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["enabled"] is True
    assert enabled.json()["config_values_json"]["file_format"] == "csv"

    org_enabled = client.get("/api/v1/connectors/enabled", headers=_headers(token, org_id))
    assert org_enabled.status_code == 200
    assert len(org_enabled.json()) == 1
    assert org_enabled.json()[0]["connector"]["name"] == "Generic emissions import"

    disabled = client.post(f"/api/v1/connectors/{connector_id}/disable", headers=_headers(token, org_id))
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False

    updated = client.patch(
        f"/api/v1/connectors/catalog/{connector_id}",
        headers=_headers(token, org_id),
        json={"description": "Updated generic connector", "enabled": False},
    )
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False

    enable_disabled_catalog = client.post(
        f"/api/v1/connectors/{connector_id}/enable",
        headers=_headers(token, org_id),
        json={"config_values_json": {"file_format": "csv"}},
    )
    assert enable_disabled_catalog.status_code == 422
    assert enable_disabled_catalog.json()["detail"] == "Connector is disabled in the catalog"

    deleted = client.delete(f"/api/v1/connectors/catalog/{connector_id}", headers=_headers(token, org_id))
    assert deleted.status_code == 200
    assert deleted.json()["deleted_at"] is not None

    missing = client.get(f"/api/v1/connectors/catalog/{connector_id}", headers=_headers(token, org_id))
    assert missing.status_code == 404

    audit_actions = {
        row.action
        for row in db_session.query(AuditLog)
        .filter(AuditLog.organization_id == uuid.UUID(org_id), AuditLog.action.like("connector.%"))
        .all()
    }
    assert {
        "connector.catalog_created",
        "connector.enabled",
        "connector.disabled",
        "connector.catalog_updated",
        "connector.catalog_deleted",
    }.issubset(audit_actions)


def test_t34_connector_org_isolation(client):
    token_a = _register(client, "t34-owner2a@example.com", "Pass1234!@", "T34 Connector Org2A")
    token_b = _register(client, "t34-owner2b@example.com", "Pass1234!@", "T34 Connector Org2B")
    org_a = _org_id(client, token_a)
    org_b = _org_id(client, token_b)

    create = client.post(
        "/api/v1/connectors/catalog",
        headers=_headers(token_a, org_a),
        json={"name": "Generic access evidence import", "category": "identity_governance", "config_schema": {}},
    )
    assert create.status_code == 201
    connector_id = create.json()["id"]

    enable_a = client.post(f"/api/v1/connectors/{connector_id}/enable", headers=_headers(token_a, org_a), json={})
    assert enable_a.status_code == 200

    enabled_b = client.get("/api/v1/connectors/enabled", headers=_headers(token_b, org_b))
    assert enabled_b.status_code == 200
    assert enabled_b.json() == []
