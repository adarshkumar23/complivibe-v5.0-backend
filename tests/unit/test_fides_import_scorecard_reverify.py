from __future__ import annotations

import uuid

from app.models.data_asset import DataAsset
from tests.helpers.auth_org import bootstrap_org_user

FIDES_IMPORT_BASE = "/api/v1/privacy/import/fides"

FIDES_MANIFEST = {
    "dataset": [
        {
            "fides_key": "customer_database",
            "name": "Customer Database",
            "description": "Primary customer records store",
            "collections": [
                {
                    "name": "users",
                    "fields": [
                        {"name": "email", "data_categories": ["user.email"]},
                        {"name": "ssn", "data_categories": ["user.government_id"]},
                        {"name": "credit_card", "data_categories": ["user.credit_card"]},
                    ],
                }
            ],
        },
        {
            "fides_key": "analytics_system",
            "name": "Analytics System",
            "description": "Operational telemetry store",
            "data_categories": ["system.operations"],
            "collections": [],
        },
        {
            "fides_key": "",
            "name": "Unnamed Dataset",
            "description": "Dataset with no fides_key",
            "collections": [],
        },
    ]
}


def test_fides_import_maps_categories_and_creates_assets(client, db_session):
    org = bootstrap_org_user(client, email_prefix="fides-import")

    response = client.post(
        FIDES_IMPORT_BASE,
        headers=org["org_headers"],
        json=FIDES_MANIFEST,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_datasets"] == 3
    assert body["assets_created"] == 3
    assert body["assets_updated"] == 0
    assert body["assets_skipped"] == 0

    assets = (
        db_session.query(DataAsset)
        .filter(
            DataAsset.organization_id == uuid.UUID(org["organization_id"]),
            DataAsset.import_source == "fides",
        )
        .all()
    )
    assert len(assets) == 3

    by_key = {a.import_key: a for a in assets}

    customer_db = by_key["customer_database"]
    assert customer_db.name == "Customer Database"
    assert customer_db.classification_source == "fides"
    # sensitive_personal_data (government_id) outranks financial_data/personal_data in priority order
    assert customer_db.classification_type == "sensitive_personal_data"
    assert customer_db.sensitivity_tier == "restricted"
    assert customer_db.classification_confirmed is False

    analytics = by_key["analytics_system"]
    assert analytics.classification_type == "operational_data"
    assert analytics.sensitivity_tier == "internal"

    unnamed = by_key.get(None) or by_key.get("")
    assert unnamed is not None
    assert unnamed.classification_type == "unclassified"
    assert unnamed.sensitivity_tier is None

    status_response = client.get(f"{FIDES_IMPORT_BASE}/status", headers=org["org_headers"])
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["import_source"] == "fides"
    assert status_body["asset_count"] == 3


def test_fides_import_reimport_updates_existing_unconfirmed_asset(client, db_session):
    org = bootstrap_org_user(client, email_prefix="fides-reimport")

    first = client.post(
        FIDES_IMPORT_BASE,
        headers=org["org_headers"],
        json={
            "dataset": [
                {
                    "fides_key": "billing_store",
                    "name": "Billing Store",
                    "description": "Initial description",
                    "collections": [
                        {"name": "invoices", "fields": [{"name": "email", "data_categories": ["user.email"]}]}
                    ],
                }
            ]
        },
    )
    assert first.status_code == 200
    assert first.json()["assets_created"] == 1

    asset = (
        db_session.query(DataAsset)
        .filter(
            DataAsset.organization_id == uuid.UUID(org["organization_id"]),
            DataAsset.import_key == "billing_store",
        )
        .one()
    )
    assert asset.classification_type == "personal_data"

    # Re-import with an updated description and a higher-priority category; since the
    # asset was never confirmed, classification fields should be refreshed on re-import.
    second = client.post(
        FIDES_IMPORT_BASE,
        headers=org["org_headers"],
        json={
            "dataset": [
                {
                    "fides_key": "billing_store",
                    "name": "Billing Store",
                    "description": "Updated description after re-scan",
                    "collections": [
                        {"name": "invoices", "fields": [{"name": "card", "data_categories": ["user.credit_card"]}]}
                    ],
                }
            ]
        },
    )
    assert second.status_code == 200
    body = second.json()
    assert body["assets_created"] == 0
    assert body["assets_updated"] == 1

    db_session.refresh(asset)
    assert asset.description == "Updated description after re-scan"
    assert asset.classification_type == "financial_data"
    assert asset.sensitivity_tier == "restricted"


def test_fides_import_requires_auth(client):
    response = client.post(FIDES_IMPORT_BASE, json=FIDES_MANIFEST)
    assert response.status_code in (401, 403)
