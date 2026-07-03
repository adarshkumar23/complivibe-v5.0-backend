from tests.helpers.auth_org import bootstrap_org_user

VENDORS_BASE = "/api/v1/compliance/vendors"


def test_verify_complete_endpoint_persists_rating_and_findings(client):
    org = bootstrap_org_user(client, email_prefix="partD-vacomplete")

    vendor = client.post(
        VENDORS_BASE,
        headers=org["org_headers"],
        json={
            "name": "PartD Vendor",
            "vendor_type": "software",
            "owner_user_id": org["user_id"],
            "risk_tier": "not_assessed",
            "status": "active",
            "data_access": True,
        },
    )
    assert vendor.status_code == 201, vendor.text
    vendor_id = vendor.json()["id"]

    assessment = client.post(
        f"{VENDORS_BASE}/{vendor_id}/assessments",
        headers=org["org_headers"],
        json={"title": "PartD Assessment", "assessment_type": "initial", "overall_rating": "not_rated"},
    )
    assert assessment.status_code == 201, assessment.text
    assessment_id = assessment.json()["id"]

    started = client.post(f"{VENDORS_BASE}/{vendor_id}/assessments/{assessment_id}/start", headers=org["org_headers"])
    assert started.status_code == 200, started.text

    completed = client.post(
        f"{VENDORS_BASE}/{vendor_id}/assessments/{assessment_id}/complete",
        headers=org["org_headers"],
        json={"overall_rating": "unsatisfactory", "findings_summary": "Real findings from PartD test"},
    )
    print("COMPLETED:", completed.status_code, completed.json())
    assert completed.status_code == 200, completed.text
    body = completed.json()
    assert body["status"] == "completed"
    assert body["overall_rating"] == "unsatisfactory", "BUG: /complete silently ignores overall_rating"
    assert body["findings_summary"] == "Real findings from PartD test", "BUG: /complete silently ignores findings_summary"

    fetched = client.get(f"{VENDORS_BASE}/{vendor_id}/assessments/{assessment_id}", headers=org["org_headers"])
    assert fetched.json()["overall_rating"] == "unsatisfactory"
    assert fetched.json()["findings_summary"] == "Real findings from PartD test"
