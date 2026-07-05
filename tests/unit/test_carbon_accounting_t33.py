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


def _ingest_key(client, token: str, org_id: str) -> str:
    response = client.post(
        "/api/v1/data-observability/lineage/openmetadata/configure",
        headers=_headers(token, org_id),
        json={"base_url": "https://metadata.example.test", "jwt_token": "test-token", "org_api_key": "carbon-ingest-key-12345"},
    )
    assert response.status_code == 200, response.text
    return response.json()["ingest_api_key"]


def test_t33_carbon_api_key_ingest_dashboard_and_audit_log(client, db_session):
    token = _register(client, "t33-owner1@example.com", "Pass1234!@", "T33 Carbon Org1")
    org_id = _org_id(client, token)
    ingest_key = _ingest_key(client, token, org_id)

    bu_response = client.post(
        "/api/v1/compliance/business-units",
        headers=_headers(token, org_id),
        json={"name": "Manufacturing", "code": "MFG"},
    )
    assert bu_response.status_code == 201, bu_response.text
    business_unit_id = bu_response.json()["id"]

    first = client.post(
        "/api/v1/carbon-accounting/readings",
        headers={"X-CompliVibe-Key": ingest_key},
        json={
            "scope": "scope1",
            "source": "utility-meter",
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
            "value": "1000.5",
            "unit": "tCO2e",
            "business_unit_id": business_unit_id,
            "source_record_id": "meter-jan",
            "raw_payload": {"meter": "M-1"},
        },
    )
    assert first.status_code == 201, first.text
    assert first.json()["organization_id"] == org_id

    second = client.post(
        "/api/v1/carbon-accounting/readings",
        headers={"X-CompliVibe-Key": ingest_key},
        json={
            "scope": "scope2",
            "source": "electricity-bill",
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
            "value": "250000",
            "unit": "kgCO2e",
        },
    )
    assert second.status_code == 201, second.text

    dashboard = client.get("/api/v1/carbon-accounting/dashboard", headers=_headers(token, org_id))
    assert dashboard.status_code == 200
    payload = dashboard.json()
    assert payload["canonical_unit"] == "tCO2e"
    assert payload["reading_count"] == 2
    assert payload["totals_by_scope"] == {"scope1": "1000.5000", "scope2": "250.0000"}
    assert payload["totals_by_period"] == [{"period": "2026-01", "value": "1250.5000"}]
    assert {"business_unit_id": business_unit_id, "value": "1000.5000"} in payload["totals_by_business_unit"]
    assert {"business_unit_id": None, "value": "250.0000"} in payload["totals_by_business_unit"]

    audits = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.organization_id == uuid.UUID(org_id),
            AuditLog.action == "carbon_accounting.reading_ingested",
        )
        .all()
    )
    assert len(audits) == 2
    assert audits[0].metadata_json["source"] == "api_key_ingest"


def test_t33_carbon_ingest_rejects_bad_key_and_bad_period(client):
    token = _register(client, "t33-owner2@example.com", "Pass1234!@", "T33 Carbon Org2")
    org_id = _org_id(client, token)
    ingest_key = _ingest_key(client, token, org_id)

    bad_key = client.post(
        "/api/v1/carbon-accounting/readings",
        headers={"X-CompliVibe-Key": "not-the-key"},
        json={
            "scope": "scope1",
            "source": "utility-meter",
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
            "value": "1",
            "unit": "tCO2e",
        },
    )
    assert bad_key.status_code == 401

    bad_period = client.post(
        "/api/v1/carbon-accounting/readings",
        headers={"X-CompliVibe-Key": ingest_key},
        json={
            "scope": "scope3",
            "source": "supplier-estimate",
            "period_start": "2026-02-01",
            "period_end": "2026-01-31",
            "value": "1",
            "unit": "tCO2e",
        },
    )
    assert bad_period.status_code == 422
    assert bad_period.json()["detail"] == "period_end must be on or after period_start"
