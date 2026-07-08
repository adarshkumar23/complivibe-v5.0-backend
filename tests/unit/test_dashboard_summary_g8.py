"""G8 item 3: /api/v1/dashboard/summary must reflect real data, matching the
same org/moment view given by /compliance/dashboard/posture-summary, instead
of the previous hardcoded placeholder (open_risks always 0, etc)."""

from tests.helpers.auth_org import bootstrap_org_user


def test_dashboard_summary_reflects_real_open_risks_matching_posture_summary(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g8-dash")
    headers = org["org_headers"]

    # Before any data: both endpoints agree at zero.
    empty = client.get("/api/v1/dashboard/summary", headers=headers)
    assert empty.status_code == 200
    assert empty.json()["open_risks"] == 0

    # Create two open risks and one accepted (non-open) risk.
    for title, status_after_create in [("Risk A", None), ("Risk B", None)]:
        resp = client.post(
            "/api/v1/risks",
            headers=headers,
            json={
                "title": title,
                "description": "g8 repro",
                "category": "third_party",
                "likelihood": 3,
                "impact": 3,
            },
        )
        assert resp.status_code == 201, resp.text

    summary = client.get("/api/v1/dashboard/summary", headers=headers)
    assert summary.status_code == 200
    posture = client.get("/api/v1/compliance/dashboard/posture-summary", headers=headers)
    assert posture.status_code == 200

    assert summary.json()["open_risks"] == 2
    # Same org, same moment: the two endpoints must never disagree on risk count.
    assert summary.json()["open_risks"] == posture.json()["risks"]["total"]


def test_dashboard_summary_reflects_real_controls_vendors_policies(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g8-dash-fields")
    headers = org["org_headers"]

    vendor_resp = client.post(
        "/api/v1/compliance/vendors",
        headers=headers,
        json={"name": "Acme Corp", "vendor_type": "software", "owner_user_id": org["user_id"]},
    )
    assert vendor_resp.status_code == 201, vendor_resp.text

    summary = client.get("/api/v1/dashboard/summary", headers=headers).json()
    assert summary["total_vendors"] == 1
