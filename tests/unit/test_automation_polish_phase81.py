import uuid
from datetime import UTC, datetime, timedelta

from app.models.automation_rule import AutomationRule
from app.models.task import Task
from tests.unit.test_automation_schedule_phase26 import (
    _create_risk_without_owner,
    _create_rule,
    _headers,
    _org_id,
    _register,
)


def test_phase81_rule_list_exposes_stale_and_schedule_context(client, db_session):
    owner = _register(client, "p81-owner-rules@example.com", "Pass1234!@", "P81 Automation Org Rules")
    org = _org_id(client, owner)
    rule_id = _create_rule(client, owner, org)
    sched = client.patch(
        f"/api/v1/automation/rules/{rule_id}/schedule",
        headers=_headers(owner, org),
        json={
            "schedule_enabled": True,
            "schedule_cadence": "hourly",
            "schedule_start_at": (datetime.now(UTC) - timedelta(hours=3)).isoformat(),
            "run_mode": "live",
        },
    )
    assert sched.status_code == 200

    row = db_session.get(AutomationRule, uuid.UUID(rule_id))
    assert row is not None
    row.last_run_at = datetime.now(UTC) - timedelta(days=8)
    row.next_run_at = datetime.now(UTC) - timedelta(hours=2)
    db_session.add(row)
    db_session.commit()

    listed = client.get("/api/v1/automation/rules", headers=_headers(owner, org))
    assert listed.status_code == 200
    body = listed.json()
    item = next(r for r in body if r["id"] == rule_id)
    assert item["stale_rule"] is True
    assert item["schedule_overdue"] is True
    assert item["hours_since_last_run"] >= 24 * 7
    assert item["schedule_drift_minutes"] >= 60
    assert "stale_rule" in item["context_flags"]
    assert "schedule_overdue" in item["context_flags"]
    assert "scheduled_rule" in item["context_flags"]


def test_phase81_execution_detail_context_and_ratios(client, db_session):
    owner = _register(client, "p81-owner-exec@example.com", "Pass1234!@", "P81 Automation Org Exec")
    org = _org_id(client, owner)
    _create_risk_without_owner(client, owner, org, "p81 risk without owner")
    rule_id = _create_rule(client, owner, org, trigger_type="manual_scan")

    run = client.post(f"/api/v1/automation/rules/{rule_id}/run", headers=_headers(owner, org))
    assert run.status_code == 200
    assert run.json()["matched_count"] >= 1

    executions = client.get("/api/v1/automation/executions", headers=_headers(owner, org))
    assert executions.status_code == 200
    row = executions.json()[0]
    assert row["duration_seconds"] is not None
    assert 0 <= row["success_ratio"] <= 1
    assert isinstance(row["had_errors"], bool)
    assert "contains_errors" not in row["context_flags"]

    detail = client.get(f"/api/v1/automation/executions/{row['id']}", headers=_headers(owner, org))
    assert detail.status_code == 200
    dbody = detail.json()
    assert dbody["duration_seconds"] is not None
    assert 0 <= dbody["success_ratio"] <= 1
    assert isinstance(dbody["action_logs"], list)


def test_phase81_run_due_respects_dry_run_mode_and_summary_context(client, db_session):
    owner = _register(client, "p81-owner-sched@example.com", "Pass1234!@", "P81 Automation Org Sched")
    org = _org_id(client, owner)
    _create_risk_without_owner(client, owner, org, "p81 sched risk")
    rule_id = _create_rule(client, owner, org)

    scheduled = client.patch(
        f"/api/v1/automation/rules/{rule_id}/schedule",
        headers=_headers(owner, org),
        json={
            "schedule_enabled": True,
            "schedule_cadence": "hourly",
            "schedule_start_at": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
            "run_mode": "dry_run",
        },
    )
    assert scheduled.status_code == 200

    before_task_count = db_session.query(Task).filter(Task.organization_id == uuid.UUID(org)).count()
    run_due = client.post(
        "/api/v1/automation/schedules/run-due",
        headers=_headers(owner, org),
        json={"dry_run": False, "limit": 25},
    )
    assert run_due.status_code == 200
    assert run_due.json()["execution_count"] >= 1
    assert all(item["dry_run"] is True for item in run_due.json()["executions"])

    after_task_count = db_session.query(Task).filter(Task.organization_id == uuid.UUID(org)).count()
    assert after_task_count == before_task_count

    summary = client.get("/api/v1/automation/summary", headers=_headers(owner, org))
    assert summary.status_code == 200
    sbody = summary.json()
    assert "execution_error_rate_last_24h" in sbody
    assert "stale_active_rules" in sbody
    assert "active_scheduled_rules_overdue" in sbody
    assert isinstance(sbody["context_flags"], list)

    schedule_summary = client.get("/api/v1/automation/schedules/summary", headers=_headers(owner, org))
    assert schedule_summary.status_code == 200
    ss = schedule_summary.json()
    assert "overdue_scheduled_rules" in ss
    assert "stalled_scheduled_rules" in ss
    assert isinstance(ss["context_flags"], list)
    assert ss["dry_run_executions_last_24h"] >= 1


def test_phase81_schedule_update_rejects_invalid_time_ranges(client):
    owner = _register(client, "p81-owner-invalid@example.com", "Pass1234!@", "P81 Automation Org Invalid")
    org = _org_id(client, owner)
    rule_id = _create_rule(client, owner, org)

    bad_range = client.patch(
        f"/api/v1/automation/rules/{rule_id}/schedule",
        headers=_headers(owner, org),
        json={
            "schedule_enabled": True,
            "schedule_cadence": "daily",
            "schedule_start_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
            "schedule_end_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        },
    )
    assert bad_range.status_code == 400

    bad_window = client.patch(
        f"/api/v1/automation/rules/{rule_id}/schedule",
        headers=_headers(owner, org),
        json={
            "schedule_enabled": True,
            "schedule_cadence": "daily",
            "schedule_window_start": "09:00",
        },
    )
    assert bad_window.status_code == 400
