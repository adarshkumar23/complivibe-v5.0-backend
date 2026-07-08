"""G8 item 1: generic (non-DORA) vendor assessment staleness must cascade the
same way the DORA ICT-register overdue path does -- (a) a flag on vendor
detail, (b) a flag on the vendor list, (c) a real alert in
/compliance/monitoring/alerts, and (d) a Risk register entry."""

from datetime import date, timedelta

from tests.helpers.auth_org import bootstrap_org_user

VENDORS_BASE = "/api/v1/compliance/vendors"
ALERTS_BASE = "/api/v1/compliance/monitoring/alerts"


def _create_vendor(client, headers, owner_user_id):
    resp = client.post(
        VENDORS_BASE,
        headers=headers,
        json={"name": "Stale Vendor Inc", "vendor_type": "software", "owner_user_id": owner_user_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_overdue_draft_assessment_cascades_to_all_four_signals(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g8-vendor-stale")
    headers = org["org_headers"]
    vendor = _create_vendor(client, headers, org["user_id"])

    overdue_due_date = (date.today() - timedelta(days=548)).isoformat()  # ~18 months ago
    resp = client.post(
        f"{VENDORS_BASE}/{vendor['id']}/assessments",
        headers=headers,
        json={"title": "Annual Security Review", "assessment_type": "periodic", "due_date": overdue_due_date},
    )
    assert resp.status_code == 201, resp.text
    assessment = resp.json()

    # (0) baseline: assessment itself reports overdue + a linked risk.
    assert assessment["status"] == "draft"
    assert assessment["is_overdue"] is True
    assert assessment["risk_id"] is not None

    # (a) vendor detail view surfaces the staleness flag.
    detail = client.get(f"{VENDORS_BASE}/{vendor['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["has_overdue_assessment"] is True

    # (b) vendor list surfaces the same flag.
    listing = client.get(VENDORS_BASE, headers=headers)
    assert listing.status_code == 200
    matching = [row for row in listing.json() if row["id"] == vendor["id"]]
    assert matching and matching[0]["has_overdue_assessment"] is True

    # (c) a real alert exists in /compliance/monitoring/alerts, not just a boolean.
    alerts = client.get(f"{ALERTS_BASE}?alert_type=vendor_assessment_overdue", headers=headers)
    assert alerts.status_code == 200
    alert_rows = alerts.json()
    assert len(alert_rows) == 1
    assert alert_rows[0]["status"] == "open"
    assert alert_rows[0]["alert_context_json"]["vendor_assessment_id"] == assessment["id"]

    # (d) a Risk register entry was created and linked.
    risk_resp = client.get(f"/api/v1/risks/{assessment['risk_id']}", headers=headers)
    assert risk_resp.status_code == 200
    risk = risk_resp.json()
    assert risk["category"] == "third_party"
    assert risk["metadata_json"]["reason"] == "assessment_overdue"
    assert risk["metadata_json"]["vendor_assessment_id"] == assessment["id"]


def test_non_overdue_assessment_produces_no_signal(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g8-vendor-fresh")
    headers = org["org_headers"]
    vendor = _create_vendor(client, headers, org["user_id"])

    future_due_date = (date.today() + timedelta(days=30)).isoformat()
    resp = client.post(
        f"{VENDORS_BASE}/{vendor['id']}/assessments",
        headers=headers,
        json={"title": "Upcoming Review", "assessment_type": "periodic", "due_date": future_due_date},
    )
    assert resp.status_code == 201
    assessment = resp.json()
    assert assessment["is_overdue"] is False
    assert assessment["risk_id"] is None

    detail = client.get(f"{VENDORS_BASE}/{vendor['id']}", headers=headers)
    assert detail.json()["has_overdue_assessment"] is False

    alerts = client.get(f"{ALERTS_BASE}?alert_type=vendor_assessment_overdue", headers=headers)
    assert alerts.json() == []


def test_repeated_update_on_already_flagged_assessment_is_idempotent(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g8-vendor-idem")
    headers = org["org_headers"]
    vendor = _create_vendor(client, headers, org["user_id"])

    overdue_due_date = (date.today() - timedelta(days=400)).isoformat()
    resp = client.post(
        f"{VENDORS_BASE}/{vendor['id']}/assessments",
        headers=headers,
        json={"title": "Annual Security Review", "assessment_type": "periodic", "due_date": overdue_due_date},
    )
    assessment = resp.json()
    first_risk_id = assessment["risk_id"]
    assert first_risk_id is not None

    update = client.patch(
        f"{VENDORS_BASE}/{vendor['id']}/assessments/{assessment['id']}",
        headers=headers,
        json={"notes": "still overdue, re-touching"},
    )
    assert update.status_code == 200
    assert update.json()["risk_id"] == first_risk_id

    alerts = client.get(f"{ALERTS_BASE}?alert_type=vendor_assessment_overdue", headers=headers)
    assert len(alerts.json()) == 1


def test_completed_assessment_past_due_date_is_not_flagged_overdue(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g8-vendor-completed")
    headers = org["org_headers"]
    vendor = _create_vendor(client, headers, org["user_id"])

    overdue_due_date = (date.today() - timedelta(days=90)).isoformat()
    resp = client.post(
        f"{VENDORS_BASE}/{vendor['id']}/assessments",
        headers=headers,
        json={"title": "Completed Review", "assessment_type": "periodic", "due_date": overdue_due_date},
    )
    assessment = resp.json()
    assert assessment["is_overdue"] is True  # draft + overdue at creation

    start = client.post(f"{VENDORS_BASE}/{vendor['id']}/assessments/{assessment['id']}/start", headers=headers)
    assert start.status_code == 200
    complete = client.post(
        f"{VENDORS_BASE}/{vendor['id']}/assessments/{assessment['id']}/complete",
        headers=headers,
        json={"overall_rating": "satisfactory", "findings_summary": "all clear"},
    )
    assert complete.status_code == 200
    assert complete.json()["status"] == "completed"
