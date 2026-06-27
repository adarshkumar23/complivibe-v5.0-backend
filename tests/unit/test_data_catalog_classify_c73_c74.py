from __future__ import annotations

from dataclasses import dataclass

from app.data_observability.services.classification_service import classify_metadata, classify_sample
from tests.helpers.auth_org import bootstrap_org_user

ASSETS_BASE = "/api/v1/data-observability/assets"


@dataclass
class _MockPresidioResult:
    entity_type: str
    score: float
    start: int
    end: int


class _MockPresidioEngine:
    def analyze(self, text: str, language: str = "en") -> list[_MockPresidioResult]:
        _ = (text, language)
        return [
            _MockPresidioResult(entity_type="PERSON", score=0.97, start=0, end=4),
            _MockPresidioResult(entity_type="EMAIL_ADDRESS", score=0.89, start=10, end=28),
        ]


def _create_asset(client, headers: dict[str, str], owner_id: str, **overrides):
    payload = {
        "name": "customer_email_database",
        "asset_type": "database",
        "owner_id": owner_id,
        "description": "Stores customer email and contact records",
        "schema_column_names": ["customer_id", "email", "phone_number"],
        "tags": ["crm", "customer"],
    }
    payload.update(overrides)
    response = client.post(ASSETS_BASE, headers=headers, json=payload)
    assert response.status_code == 201
    return response


def test_c73_data_asset_catalog_flow(client):
    org = bootstrap_org_user(client, email_prefix="c73-org")

    created = _create_asset(client, org["org_headers"], org["user_id"])
    body = created.json()
    assert body["classification_type"] == "personal_data"
    assert float(body["classification_confidence"]) > 0.70
    assert body["classification_confirmed"] is False
    assert body["classification_source"] == "metadata_rules"

    unmatched = _create_asset(
        client,
        org["org_headers"],
        org["user_id"],
        name="unknown_xyz_table",
        description="miscellaneous alpha beta records",
        schema_column_names=["alpha", "beta"],
        tags=[],
    )
    unmatched_body = unmatched.json()
    assert unmatched_body["classification_type"] == "unclassified"
    assert float(unmatched_body["classification_confidence"] or 0.0) == 0.0
    assert unmatched_body["classification_confirmed"] is False

    confirmed = client.post(
        f"{ASSETS_BASE}/{body['id']}/confirm-classification",
        headers=org["org_headers"],
        json={
            "classification_type": "personal_data",
            "sensitivity_tier": "restricted",
        },
    )
    assert confirmed.status_code == 200
    confirmed_body = confirmed.json()
    assert confirmed_body["classification_confirmed"] is True
    assert confirmed_body["classification_source"] == "manual"
    assert confirmed_body["sensitivity_tier"] == "restricted"

    updated = client.patch(
        f"{ASSETS_BASE}/{unmatched_body['id']}",
        headers=org["org_headers"],
        json={
            "name": "health_records_patient",
            "description": "patient diagnosis and treatment history",
        },
    )
    assert updated.status_code == 200
    updated_body = updated.json()
    assert updated_body["classification_type"] == "health_data"
    assert updated_body["classification_confirmed"] is False

    filtered = client.get(f"{ASSETS_BASE}?classification_confirmed=false", headers=org["org_headers"])
    assert filtered.status_code == 200
    assert all(item["classification_confirmed"] is False for item in filtered.json())

    summary = client.get(f"{ASSETS_BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["total_assets"] == 2
    assert summary_body["confirmed_count"] == 1
    assert summary_body["unconfirmed_count"] == 1
    assert summary_body["by_classification_type"]["personal_data"] >= 1
    assert summary_body["by_classification_type"]["health_data"] >= 1

    org_b = bootstrap_org_user(client, email_prefix="c73-org-b")
    isolated = client.get(f"{ASSETS_BASE}/{body['id']}", headers=org_b["org_headers"])
    assert isolated.status_code == 404


def test_c74_classification_engine(monkeypatch, client):
    personal = classify_metadata("ssn_records", "contains email and name", ["ssn", "email"])
    assert personal["classification_type"] == "personal_data"
    assert personal["confidence"] >= 0.70

    health = classify_metadata("health_records_patient", "clinical diagnosis table", ["patient_id", "diagnosis"])
    assert health["classification_type"] == "health_data"

    operational = classify_metadata("audit_log_table", "system telemetry events", ["span_id", "event"])
    assert operational["classification_type"] == "operational_data"

    unknown = classify_metadata("unknown_xyz_table", "foobar", ["alpha", "beta"])
    assert unknown["classification_type"] == "unclassified"
    assert unknown["confidence"] == 0.0

    boosted = classify_metadata(
        "customer_email_phone_address_table",
        "contains contact details and dob",
        ["firstname", "lastname", "email", "dob"],
    )
    assert boosted["classification_type"] == "personal_data"
    assert boosted["confidence"] > 0.70

    from app.data_observability.services import classification_service

    monkeypatch.setattr(classification_service, "get_presidio", lambda: _MockPresidioEngine())
    sample_result = classify_sample("John Doe, john@example.com")
    assert sample_result["status"] == "success"
    assert sample_result["suggested_classification"] == "personal_data"
    assert sample_result["warning"] is not None
    assert "Human review" in sample_result["warning"]

    monkeypatch.setattr(classification_service, "get_presidio", lambda: None)
    unavailable_result = classify_sample("any")
    assert unavailable_result["status"] == "unavailable"

    org = bootstrap_org_user(client, email_prefix="c74-org")
    asset = _create_asset(
        client,
        org["org_headers"],
        org["user_id"],
        name="sample_text_asset",
        description="sample driven classification target",
        schema_column_names=["note"],
    ).json()

    monkeypatch.setattr(classification_service, "get_presidio", lambda: _MockPresidioEngine())
    sample_api = client.post(
        f"{ASSETS_BASE}/{asset['id']}/classify-sample",
        headers=org["org_headers"],
        json={"sample_text": "Jane Doe, jane@example.com"},
    )
    assert sample_api.status_code == 200
    assert sample_api.json()["suggested_classification"] == "personal_data"

    # Explicit sample classification never auto-confirms the asset.
    refreshed = client.get(f"{ASSETS_BASE}/{asset['id']}", headers=org["org_headers"])
    assert refreshed.status_code == 200
    assert refreshed.json()["classification_confirmed"] is False
