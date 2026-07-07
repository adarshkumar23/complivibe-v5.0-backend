from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import uuid

from app.models.data_asset import DataAsset

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
    assert "context_flags" in body
    assert "classification_unconfirmed" in body["context_flags"]
    assert body["recommended_review"] == "confirm_classification"

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
    assert confirmed_body["recommended_review"] is None

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
    assert "stale_classification_count" in summary_body
    assert "high_risk_unconfirmed_count" in summary_body

    org_b = bootstrap_org_user(client, email_prefix="c73-org-b")
    isolated = client.get(f"{ASSETS_BASE}/{body['id']}", headers=org_b["org_headers"])
    assert isolated.status_code == 404


def test_item7_explicit_sensitivity_tier_is_not_silently_overridden_by_auto_classification(client):
    org = bootstrap_org_user(client, email_prefix="item7-org")

    # This name/description/columns combo would auto-classify to "personal_data" /
    # "confidential" via metadata_rules (see test_c73 above) if sensitivity_tier were
    # left unset. Here the caller explicitly provides a different, lower tier.
    created = _create_asset(
        client,
        org["org_headers"],
        org["user_id"],
        sensitivity_tier="public",
    )
    body = created.json()
    assert body["sensitivity_tier"] == "public"
    assert body["classification_source"] == "manual"

    # Auto-classification still runs when no explicit tier is provided.
    auto_created = _create_asset(client, org["org_headers"], org["user_id"], name="another_customer_email_db")
    auto_body = auto_created.json()
    assert auto_body["sensitivity_tier"] == "confidential"
    assert auto_body["classification_source"] == "metadata_rules"


def test_data_asset_owner_and_custodian_must_be_org_members(client):
    org = bootstrap_org_user(client, email_prefix="data-owner-scope-a")
    org_b = bootstrap_org_user(client, email_prefix="data-owner-scope-b")

    foreign_owner = client.post(
        ASSETS_BASE,
        headers=org["org_headers"],
        json={
            "name": "foreign_owner_asset",
            "asset_type": "database",
            "owner_id": org_b["user_id"],
            "description": "contains customer email",
            "schema_column_names": ["email"],
            "tags": ["probe"],
        },
    )
    assert foreign_owner.status_code == 422
    assert foreign_owner.json()["detail"] == "owner_id must be an active organization user"

    asset = _create_asset(client, org["org_headers"], org["user_id"], name="owned_asset").json()
    foreign_custodian = client.patch(
        f"{ASSETS_BASE}/{asset['id']}",
        headers=org["org_headers"],
        json={"custodian_id": org_b["user_id"]},
    )
    assert foreign_custodian.status_code == 422
    assert foreign_custodian.json()["detail"] == "custodian_id must be an active organization user"

    own_custodian = client.patch(
        f"{ASSETS_BASE}/{asset['id']}",
        headers=org["org_headers"],
        json={"custodian_id": org["user_id"]},
    )
    assert own_custodian.status_code == 200
    assert own_custodian.json()["custodian_id"] == org["user_id"]


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


def test_data_asset_context_flags_stale_and_summary_risk_insight(client, db_session):
    org = bootstrap_org_user(client, email_prefix="c73-stale-org")
    created = _create_asset(
        client,
        org["org_headers"],
        org["user_id"],
        name="stale_financial_records",
        description="bank account and transaction dataset",
        schema_column_names=["account_number", "transaction_amount"],
    )
    assert created.status_code == 201
    asset_id = created.json()["id"]

    row = db_session.query(DataAsset).filter(DataAsset.id == uuid.UUID(asset_id)).one()
    row.updated_at = datetime.now(UTC) - timedelta(days=45)
    db_session.add(row)
    db_session.commit()

    fetched = client.get(f"{ASSETS_BASE}/{asset_id}", headers=org["org_headers"])
    assert fetched.status_code == 200
    payload = fetched.json()
    assert payload["classification_stale"] is True
    assert "classification_stale" in payload["context_flags"]
    assert payload["recommended_review"] == "confirm_classification"

    summary = client.get(f"{ASSETS_BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    body = summary.json()
    assert body["stale_classification_count"] >= 1
    assert body["high_risk_unconfirmed_count"] >= 1
