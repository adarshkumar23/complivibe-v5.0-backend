from __future__ import annotations

import datetime as dt
import uuid

from app.privacy.services.rbi_dpdp_reconciliation_service import RBIDPDPReconciliationService
from tests.helpers.auth_org import bootstrap_org_user

ASSETS_BASE = "/api/v1/data-observability/assets"
DSR_BASE = "/api/v1/privacy/dsr"


def test_explain_blocks_when_no_relationship_end_date_on_file(db_session):
    service = RBIDPDPReconciliationService(db_session)
    result = service.explain(uuid.uuid4(), "kyc_identity_documents", relationship_end_date=None)
    assert result["blocked"] is True
    assert result["retention_until"] is None
    assert "cannot be confirmed" in result["reason"] or "flagged" in result["reason"].lower()
    assert len(result["citations"]) == 2


def test_explain_blocks_while_retention_floor_has_not_lapsed():
    service = RBIDPDPReconciliationService(None)
    today = dt.date(2026, 7, 10)
    end_date = dt.date(2024, 1, 1)  # 2 years ago, floor is 5 years
    result = service.explain(uuid.uuid4(), "transaction_records", relationship_end_date=end_date, today=today)
    assert result["blocked"] is True
    assert result["retention_until"] == "2029-01-01"
    assert result["erasure_available_from"] == "2029-01-01"


def test_explain_unblocks_once_retention_floor_has_lapsed():
    service = RBIDPDPReconciliationService(None)
    today = dt.date(2026, 7, 10)
    end_date = dt.date(2019, 1, 1)  # 7 years ago, floor is 5 years -> lapsed 2024-01-01
    result = service.explain(uuid.uuid4(), "kyc_identity_documents", relationship_end_date=end_date, today=today)
    assert result["blocked"] is False
    assert result["retention_until"] == "2024-01-01"


def test_explain_no_floor_mapped_for_unknown_category(db_session):
    service = RBIDPDPReconciliationService(db_session)
    result = service.explain(uuid.uuid4(), "marketing_preferences", relationship_end_date=None)
    assert result["blocked"] is False
    assert result["citations"] == []


def test_payment_data_localization_exposure_flags_non_india_assets(client, db_session):
    org = bootstrap_org_user(client, email_prefix="rbi-localization")
    org_id = uuid.UUID(org["organization_id"])

    exposed = client.post(
        ASSETS_BASE,
        headers=org["org_headers"],
        json={
            "name": "us-hosted-payments-table",
            "asset_type": "table",
            "owner_id": org["user_id"],
            "geographic_locations": ["US"],
        },
    )
    assert exposed.status_code == 201
    patch1 = client.patch(
        f"{ASSETS_BASE}/{exposed.json()['id']}",
        headers=org["org_headers"],
        json={"classification_type": "financial_data"},
    )
    assert patch1.status_code == 200

    compliant = client.post(
        ASSETS_BASE,
        headers=org["org_headers"],
        json={
            "name": "india-hosted-payments-table",
            "asset_type": "table",
            "owner_id": org["user_id"],
            "geographic_locations": ["IN-Mumbai"],
        },
    )
    assert compliant.status_code == 201
    patch2 = client.patch(
        f"{ASSETS_BASE}/{compliant.json()['id']}",
        headers=org["org_headers"],
        json={"classification_type": "financial_data"},
    )
    assert patch2.status_code == 200

    service = RBIDPDPReconciliationService(db_session)
    exposures = service.check_payment_data_localization_exposure(org_id)
    exposed_names = {item["asset_name"] for item in exposures}
    assert "us-hosted-payments-table" in exposed_names
    assert "india-hosted-payments-table" not in exposed_names


def test_erasure_request_with_real_engine_blocks_then_unblocks_after_floor_lapses(client):
    org = bootstrap_org_user(client, email_prefix="rbi-e2e")

    create = client.post(
        DSR_BASE,
        headers=org["org_headers"],
        json={
            "request_type": "erasure",
            "subject_name": "Jane Principal",
            "subject_email": "jane@example.io",
            "regulatory_framework": "dpdp",
            "data_categories": ["kyc_identity_documents"],
            "relationship_end_date": "2024-01-01",
        },
    )
    assert create.status_code == 201
    request_id = create.json()["id"]

    client.post(f"{DSR_BASE}/{request_id}/verify-identity", headers=org["org_headers"])

    blocked = client.post(
        f"{DSR_BASE}/{request_id}/transition",
        headers=org["org_headers"],
        json={"new_status": "fulfilled"},
    )
    assert blocked.status_code == 409
    detail = blocked.json()["detail"]
    assert "2029-01-01" in str(detail)
