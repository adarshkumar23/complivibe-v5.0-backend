from datetime import date, timedelta
from tests.helpers.auth_org import bootstrap_org_user

SCHEDULE_BASE = "/api/v1/compliance/audit-schedules"
ENGAGEMENT_BASE = "/api/v1/compliance/audit-engagements"


def _framework_id(client, headers):
    resp = client.get("/api/v1/frameworks", headers=headers)
    assert resp.status_code == 200
    return resp.json()[0]["id"]


def test_verify_schedule_history_scoped_to_own_schedule_not_all_org_engagements(client):
    org = bootstrap_org_user(client, email_prefix="partD-schedhist")
    fw_id = _framework_id(client, org["org_headers"])

    schedule_a = client.post(
        SCHEDULE_BASE,
        headers=org["org_headers"],
        json={
            "title": "Schedule A",
            "audit_type": "internal_readiness",
            "framework_id": fw_id,
            "recurrence_pattern": "annual",
            "next_audit_date": (date.today() + timedelta(days=5)).isoformat(),
            "preparation_reminder_days": 30,
        },
    )
    assert schedule_a.status_code == 201, schedule_a.text
    schedule_a_id = schedule_a.json()["id"]

    # A manually-created engagement, unrelated to any schedule -- must NOT show up
    # in schedule_a's history.
    unrelated = client.post(
        ENGAGEMENT_BASE,
        headers=org["org_headers"],
        json={
            "title": "Unrelated manual engagement",
            "audit_type": "internal_readiness",
            "scope_framework_ids": [fw_id],
            "assigned_auditor_ids": [org["user_id"]],
            "start_date": (date.today() + timedelta(days=5)).isoformat(),
            "end_date": (date.today() + timedelta(days=20)).isoformat(),
        },
    )
    assert unrelated.status_code == 201, unrelated.text

    history = client.get(f"{SCHEDULE_BASE}/{schedule_a_id}/history", headers=org["org_headers"])
    print("HISTORY:", history.status_code, history.json())
    assert history.status_code == 200
    assert history.json() == [], (
        "BUG: schedule history is unscoped and leaks unrelated org engagements"
    )
