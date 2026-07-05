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
            "emission_factor_source": "epa_egrid",
            "emission_factor_version": "eGRID2023rev1",
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
            "scope3_category": "business_travel",
            "source": "supplier-estimate",
            "period_start": "2026-02-01",
            "period_end": "2026-01-31",
            "value": "1",
            "unit": "tCO2e",
        },
    )
    assert bad_period.status_code == 422
    assert bad_period.json()["detail"] == "period_end must be on or after period_start"


def test_t33_carbon_scope3_requires_category_and_rejects_lump_sum(client):
    token = _register(client, "t33-owner3@example.com", "Pass1234!@", "T33 Carbon Org3")
    org_id = _org_id(client, token)
    ingest_key = _ingest_key(client, token, org_id)

    missing_category = client.post(
        "/api/v1/carbon-accounting/readings",
        headers={"X-CompliVibe-Key": ingest_key},
        json={
            "scope": "scope3",
            "source": "supplier-estimate",
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
            "value": "500",
            "unit": "tCO2e",
        },
    )
    assert missing_category.status_code == 422, missing_category.text

    category_on_scope1 = client.post(
        "/api/v1/carbon-accounting/readings",
        headers={"X-CompliVibe-Key": ingest_key},
        json={
            "scope": "scope1",
            "scope3_category": "business_travel",
            "source": "fleet-fuel",
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
            "value": "10",
            "unit": "tCO2e",
        },
    )
    assert category_on_scope1.status_code == 422, category_on_scope1.text

    invalid_category = client.post(
        "/api/v1/carbon-accounting/readings",
        headers={"X-CompliVibe-Key": ingest_key},
        json={
            "scope": "scope3",
            "scope3_category": "not_a_real_category",
            "source": "supplier-estimate",
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
            "value": "500",
            "unit": "tCO2e",
        },
    )
    assert invalid_category.status_code == 422, invalid_category.text

    ok = client.post(
        "/api/v1/carbon-accounting/readings",
        headers={"X-CompliVibe-Key": ingest_key},
        json={
            "scope": "scope3",
            "scope3_category": "business_travel",
            "source": "supplier-estimate",
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
            "value": "500",
            "unit": "tCO2e",
        },
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["scope3_category"] == "business_travel"


def test_t33_carbon_reingest_same_source_record_corrects_instead_of_duplicating(client, db_session):
    token = _register(client, "t33-owner4@example.com", "Pass1234!@", "T33 Carbon Org4")
    org_id = _org_id(client, token)
    ingest_key = _ingest_key(client, token, org_id)

    payload = {
        "scope": "scope1",
        "source": "utility-meter",
        "period_start": "2026-01-01",
        "period_end": "2026-01-31",
        "value": "1000",
        "unit": "tCO2e",
        "source_record_id": "meter-jan-2026",
    }
    first = client.post("/api/v1/carbon-accounting/readings", headers={"X-CompliVibe-Key": ingest_key}, json=payload)
    assert first.status_code == 201, first.text
    reading_id = first.json()["id"]

    corrected_payload = dict(payload, value="875.25")
    second = client.post("/api/v1/carbon-accounting/readings", headers={"X-CompliVibe-Key": ingest_key}, json=corrected_payload)
    assert second.status_code == 201, second.text
    assert second.json()["id"] == reading_id, "resubmitting the same source_record_id must correct in place, not duplicate"
    assert second.json()["value"] == "875.2500"
    assert second.json()["corrected_at"] is not None

    dashboard = client.get("/api/v1/carbon-accounting/dashboard", headers=_headers(token, org_id))
    assert dashboard.status_code == 200
    payload_json = dashboard.json()
    assert payload_json["reading_count"] == 1
    assert payload_json["totals_by_scope"] == {"scope1": "875.2500"}

    audits = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.organization_id == uuid.UUID(org_id),
            AuditLog.action == "carbon_accounting.reading_corrected",
        )
        .all()
    )
    assert len(audits) == 1
    assert audits[0].before_json["value"] == "1000.0000"
    assert audits[0].after_json["value"] == "875.25"


def test_t33_carbon_dashboard_flags_missing_scope3_and_stale_emission_factor(client):
    token = _register(client, "t33-owner5@example.com", "Pass1234!@", "T33 Carbon Org5")
    org_id = _org_id(client, token)
    ingest_key = _ingest_key(client, token, org_id)

    r1 = client.post(
        "/api/v1/carbon-accounting/readings",
        headers={"X-CompliVibe-Key": ingest_key},
        json={
            "scope": "scope2",
            "source": "electricity-bill",
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
            "value": "100",
            "unit": "tCO2e",
            "emission_factor_source": "epa_egrid",
            "emission_factor_version": "eGRID2019",
        },
    )
    assert r1.status_code == 201, r1.text

    dashboard = client.get("/api/v1/carbon-accounting/dashboard", headers=_headers(token, org_id))
    assert dashboard.status_code == 200
    insights = dashboard.json()["insights"]
    assert any("Scope 3" in i for i in insights)
    assert any("eGRID2019" in i for i in insights)
