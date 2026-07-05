from __future__ import annotations

import uuid
from datetime import date, timedelta

import sqlalchemy as sa

from app.models.issue import Issue
from app.models.resilience_testing import ResilienceTest
from tests.helpers.auth_org import bootstrap_org_user


def _create_test(client, headers, **overrides):
    payload = {
        "test_type": "tabletop",
        "scope": "Core payment processing systems",
        "scheduled_date": date.today().isoformat(),
        "owner_team": "Security",
    }
    payload.update(overrides)
    return client.post("/api/v1/resilience-tests", headers=headers, json=payload)


def test_resilience_testing_permissions_seeded(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="resilience-perms")

    rows = db_session.execute(
        sa.text(
            "SELECT key FROM permissions WHERE key IN ('resilience_testing:read', 'resilience_testing:manage')"
        )
    ).scalars().all()
    assert set(rows) == {"resilience_testing:read", "resilience_testing:manage"}

    response = client.get("/api/v1/auth/permissions", headers=org_user["org_headers"])
    assert response.status_code == 200, response.text
    codes = response.json()["permission_codes"]
    assert "resilience_testing:read" in codes
    assert "resilience_testing:manage" in codes


def test_create_and_complete_happy_path_creates_issue(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="resilience-happy")
    headers = org_user["org_headers"]

    resp = _create_test(client, headers)
    assert resp.status_code == 201, resp.text
    test = resp.json()
    assert test["status"] == "scheduled"
    test_id = test["id"]

    complete_resp = client.post(
        f"/api/v1/resilience-tests/{test_id}/complete",
        headers=headers,
        json={
            "results_json": {
                "summary": "Found gaps in failover procedure",
                "findings": [
                    {"description": "Failover runbook is outdated", "severity": "high"},
                    {"description": "Minor documentation typo", "severity": "low"},
                ],
            }
        },
    )
    assert complete_resp.status_code == 200, complete_resp.text
    body = complete_resp.json()
    assert body["test"]["status"] == "completed"
    assert body["test"]["findings_count"] == 2
    assert len(body["issues_created"]) == 1

    issue_id = uuid.UUID(body["issues_created"][0])
    issue_row = db_session.execute(sa.select(Issue).where(Issue.id == issue_id)).scalar_one()
    assert issue_row.source_type == "risk_assessment"
    assert str(issue_row.source_id) == test_id
    assert issue_row.severity == "high"


def test_completing_twice_does_not_duplicate_issue(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="resilience-idempotent")
    headers = org_user["org_headers"]

    resp = _create_test(client, headers)
    assert resp.status_code == 201, resp.text
    test_id = resp.json()["id"]

    results_payload = {
        "results_json": {
            "summary": "Critical finding",
            "findings": [{"description": "Backup restore failed", "severity": "critical"}],
        }
    }

    first = client.post(f"/api/v1/resilience-tests/{test_id}/complete", headers=headers, json=results_payload)
    assert first.status_code == 200, first.text
    assert len(first.json()["issues_created"]) == 1

    second = client.post(f"/api/v1/resilience-tests/{test_id}/complete", headers=headers, json=results_payload)
    assert second.status_code == 200, second.text
    assert len(second.json()["issues_created"]) == 0

    count = db_session.execute(
        sa.select(sa.func.count()).select_from(Issue).where(
            Issue.source_type == "risk_assessment",
            Issue.source_id == uuid.UUID(test_id),
        )
    ).scalar_one()
    assert count == 1


def test_overdue_org_with_zero_tests_flags_all_types(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="resilience-zero")
    headers = org_user["org_headers"]

    resp = client.get("/api/v1/resilience-tests/overdue", headers=headers)
    assert resp.status_code == 200, resp.text
    entries = resp.json()
    by_type = {}
    for entry in entries:
        by_type.setdefault(entry["test_type"], []).append(entry)

    assert any(e["is_overdue"] for e in by_type.get("threat_led_pen_test", []))
    assert any(e["is_overdue"] for e in by_type.get("tabletop", []))
    assert any(e["is_overdue"] for e in by_type.get("simulation", []))
    for entry in entries:
        assert entry["reason"]


def test_overdue_tabletop_cadence(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="resilience-tabletop")
    headers = org_user["org_headers"]
    organization_id = uuid.UUID(org_user["organization_id"])

    overdue_test = ResilienceTest(
        organization_id=organization_id,
        test_type="tabletop",
        scope="Overdue tabletop",
        scheduled_date=date.today() - timedelta(days=410),
        completed_date=date.today() - timedelta(days=400),
        status="completed",
        findings_count=0,
    )
    fresh_test = ResilienceTest(
        organization_id=organization_id,
        test_type="tabletop",
        scope="Recent tabletop",
        scheduled_date=date.today() - timedelta(days=40),
        completed_date=date.today() - timedelta(days=30),
        status="completed",
        findings_count=0,
    )
    db_session.add_all([overdue_test, fresh_test])
    db_session.commit()

    resp = client.get("/api/v1/resilience-tests/overdue", headers=headers)
    assert resp.status_code == 200, resp.text
    entries = [e for e in resp.json() if e["test_type"] == "tabletop"]
    # Most recent completed tabletop test is the fresh one (30 days ago) -> not overdue.
    aggregate_entry = next(e for e in entries if e["last_completed_date"] is not None)
    assert aggregate_entry["is_overdue"] is False


def test_overdue_threat_led_pen_test_cadence(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="resilience-tlpt")
    headers = org_user["org_headers"]
    organization_id = uuid.UUID(org_user["organization_id"])

    within_window_test = ResilienceTest(
        organization_id=organization_id,
        test_type="threat_led_pen_test",
        scope="TLPT within window",
        scheduled_date=date.today() - timedelta(days=740),
        completed_date=date.today() - timedelta(days=730),
        status="completed",
        findings_count=0,
    )
    db_session.add(within_window_test)
    db_session.commit()

    resp = client.get("/api/v1/resilience-tests/overdue", headers=headers)
    assert resp.status_code == 200, resp.text
    tlpt_entry = next(e for e in resp.json() if e["test_type"] == "threat_led_pen_test")
    assert tlpt_entry["is_overdue"] is False

    # Now push it beyond the 3-year cadence.
    within_window_test.completed_date = date.today() - timedelta(days=1500)
    db_session.commit()

    resp2 = client.get("/api/v1/resilience-tests/overdue", headers=headers)
    assert resp2.status_code == 200, resp2.text
    tlpt_entry2 = next(e for e in resp2.json() if e["test_type"] == "threat_led_pen_test")
    assert tlpt_entry2["is_overdue"] is True


def test_missed_scheduled_test_flagged_overdue(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="resilience-missed")
    headers = org_user["org_headers"]
    organization_id = uuid.UUID(org_user["organization_id"])

    missed_test = ResilienceTest(
        organization_id=organization_id,
        test_type="simulation",
        scope="Missed simulation",
        scheduled_date=date.today() - timedelta(days=10),
        status="scheduled",
        findings_count=0,
    )
    db_session.add(missed_test)
    db_session.commit()

    resp = client.get("/api/v1/resilience-tests/overdue", headers=headers)
    assert resp.status_code == 200, resp.text
    reasons = [e["reason"] for e in resp.json() if e["test_type"] == "simulation"]
    assert any("scheduled" in r.lower() and "overdue" in r.lower() for r in reasons)


def test_invalid_test_type_returns_422(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="resilience-badtype")
    headers = org_user["org_headers"]

    resp = _create_test(client, headers, test_type="not_a_real_type")
    assert resp.status_code == 422, resp.text


def test_malformed_finding_severity_returns_422(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="resilience-badfinding")
    headers = org_user["org_headers"]

    resp = _create_test(client, headers)
    assert resp.status_code == 201, resp.text
    test_id = resp.json()["id"]

    complete_resp = client.post(
        f"/api/v1/resilience-tests/{test_id}/complete",
        headers=headers,
        json={
            "results_json": {
                "summary": "bad severity",
                "findings": [{"description": "oops", "severity": "not_a_severity"}],
            }
        },
    )
    assert complete_resp.status_code == 422, complete_resp.text


def test_completing_cancelled_test_returns_4xx(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="resilience-cancelled")
    headers = org_user["org_headers"]

    resp = _create_test(client, headers)
    assert resp.status_code == 201, resp.text
    test_id = resp.json()["id"]

    patch_resp = client.patch(
        f"/api/v1/resilience-tests/{test_id}",
        headers=headers,
        json={"status": "cancelled"},
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert patch_resp.json()["status"] == "cancelled"

    complete_resp = client.post(
        f"/api/v1/resilience-tests/{test_id}/complete",
        headers=headers,
        json={"results_json": {"summary": "n/a", "findings": []}},
    )
    assert 400 <= complete_resp.status_code < 500, complete_resp.text
