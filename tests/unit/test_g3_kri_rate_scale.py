from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.models.task import Task
from tests.helpers.auth_org import bootstrap_org_user

RISK_INDICATORS_BASE = "/api/v1/compliance/risk-indicators"


def test_rate_kri_breach_fires_with_realistic_percentage_threshold(client, db_session):
    """G3 item 3: rate-type KRI metrics (control_expiry_rate/evidence_gap_rate/
    overdue_task_rate) previously returned a 0-1 fraction but thresholds were
    entered/compared on a 0-100 scale, so a compliance officer entering a realistic
    "flag when overdue-task rate exceeds 80%" threshold as warning=60/critical=80
    would NEVER breach (a computed 0.85 fraction is always < 80). This proves a
    realistic KRI (85% of tasks overdue, threshold 80%) now correctly breaches.
    """
    org = bootstrap_org_user(client, email_prefix="g3-kri-scale")
    headers = org["org_headers"]
    org_id = uuid.UUID(org["organization_id"])
    owner_id = org["user_id"]
    now = datetime.now(UTC)

    # 17 overdue / 20 total = 85% overdue -- a realistic, severe KRI value.
    tasks = []
    for i in range(17):
        tasks.append(Task(organization_id=org_id, title=f"Overdue {i}", status="open", due_date=now - timedelta(days=1), task_type="general"))
    for i in range(3):
        tasks.append(Task(organization_id=org_id, title=f"On-time {i}", status="open", due_date=now + timedelta(days=5), task_type="general"))
    db_session.add_all(tasks)
    db_session.commit()

    create_resp = client.post(
        RISK_INDICATORS_BASE,
        headers=headers,
        json={
            "name": "Overdue Task Rate KRI",
            "metric_type": "overdue_task_rate",
            "target_value": 10,
            "warning_threshold": 60,
            "critical_threshold": 80,
            "owner_user_id": owner_id,
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    indicator_id = create_resp.json()["id"]

    recompute = client.post(f"{RISK_INDICATORS_BASE}/{indicator_id}/recalculate", headers=headers)
    assert recompute.status_code == 200, recompute.text
    body = recompute.json()
    print("KRI RESULT:", body["current_value"], body["status"])
    assert abs(body["current_value"] - 85.0) < 0.5, body
    assert body["status"] == "red", (
        f"expected an 85% overdue rate to breach an 80 (percentage-scale) critical threshold, got: {body}"
    )


def test_rate_kri_rejects_fraction_scale_threshold_as_invalid(client, db_session):
    """Defense-in-depth: entering a 0-1 fraction as a threshold for a rate metric
    (the exact mismatch that caused the original bug) is now rejected outright
    rather than silently accepted and never breaching.
    """
    org = bootstrap_org_user(client, email_prefix="g3-kri-scale-reject")
    headers = org["org_headers"]
    owner_id = org["user_id"]

    resp = client.post(
        RISK_INDICATORS_BASE,
        headers=headers,
        json={
            "name": "Bad scale KRI",
            "metric_type": "overdue_task_rate",
            "target_value": 0.1,
            "warning_threshold": 0.4,
            "critical_threshold": 150,
            "owner_user_id": owner_id,
        },
    )
    assert resp.status_code == 422, resp.text
