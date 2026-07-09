from __future__ import annotations

from tests.helpers.auth_org import bootstrap_org_user

DPA_BASE = "/api/v1/privacy/dpas"
ROPA_BASE = "/api/v1/privacy/ropa"


def _create_activity(client, headers, owner_id, **overrides):
    payload = {
        "name": "Realistic activity",
        "description": "Processing",
        "purpose": "Service operations",
        "legal_basis": "contract",
        "data_categories": ["personal_data"],
        "special_categories": [],
        "data_subject_types": ["customers"],
        "retention_period": "1 year",
        "recipients": ["internal"],
        "international_transfers": False,
        "status": "active",
        "risk_level": "medium",
        "owner_id": owner_id,
        "linked_data_asset_ids": [],
        "linked_subprocessor_ids": [],
    }
    payload.update(overrides)
    response = client.post(f"{ROPA_BASE}/activities", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_gdpr_coverage_recognizes_realistic_personal_data_taxonomy(client, db_session):
    """G3 item 4: the GDPR-coverage metric previously only matched the literal string
    "personal_data" against ProcessingActivity.data_categories, missing realistic
    real-world category tags like "email", "ssn", "phone", "name", "biometric",
    "health", "financial" etc. This creates 6 activities tagged with realistic
    (non-"personal_data"-literal) categories and confirms all 6 are recognized as
    personal-data activities in the GDPR coverage summary, plus one activity with a
    clearly non-personal category that must NOT be counted.
    """
    org = bootstrap_org_user(client, email_prefix="g3-dpa-taxonomy")
    headers = org["org_headers"]
    owner_id = org["user_id"]

    realistic_categories = [
        ["email"],
        ["ssn"],
        ["phone_number"],
        ["full_name"],
        ["biometric_data"],
        ["health_data"],
    ]
    for i, categories in enumerate(realistic_categories):
        _create_activity(client, headers, owner_id, name=f"Activity {i}", data_categories=categories)

    # A genuinely non-personal-data category must NOT be swept in as a false positive.
    _create_activity(client, headers, owner_id, name="Non-personal activity", data_categories=["internal_metrics"])

    summary = client.get(f"{DPA_BASE}/summary", headers=headers)
    assert summary.status_code == 200, summary.text
    body = summary.json()
    print("GDPR COVERAGE:", body["gdpr_coverage"])
    assert body["gdpr_coverage"]["total_personal_data_activities"] == 6, (
        f"expected the 6 realistically-tagged activities to be recognized as personal data, got: {body['gdpr_coverage']}"
    )
