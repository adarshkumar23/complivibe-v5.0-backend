from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.models.audit_log import AuditLog
from app.models.issue import Issue
from app.services.scoring_service import ScoringService
from tests.helpers.auth_org import bootstrap_org_user


ISSUES_BASE = "/api/v1/compliance/issues"
POLICIES_BASE = "/api/v1/compliance/policies"
CONTROLS_BASE = "/api/v1/controls"


def _create_issue(client, headers: dict[str, str], owner_id: str, *, title: str, severity: str = "medium") -> dict:
    resp = client.post(
        ISSUES_BASE,
        headers=headers,
        json={
            "title": title,
            "description": "Issue description",
            "issue_type": "custom",
            "severity": severity,
            "source_type": "manual",
            "owner_id": owner_id,
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _create_policy(client, headers: dict[str, str], owner_id: str, *, title: str) -> dict:
    resp = client.post(
        POLICIES_BASE,
        headers=headers,
        json={
            "title": title,
            "policy_type": "acceptable_use",
            "owner_user_id": owner_id,
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _create_control(client, headers: dict[str, str], *, title: str) -> dict:
    resp = client.post(
        CONTROLS_BASE,
        headers=headers,
        json={
            "title": title,
            "control_type": "process",
            "criticality": "high",
        },
    )
    assert resp.status_code == 201
    return resp.json()


def test_a66_issue_policy_linking_and_policy_metrics(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a66-main")
    org_b = bootstrap_org_user(client, email_prefix="a66-other")

    policy = _create_policy(client, org["org_headers"], org["user_id"], title="Access Policy")
    issue_1 = _create_issue(client, org["org_headers"], org["user_id"], title="Issue-1", severity="high")
    issue_2 = _create_issue(client, org["org_headers"], org["user_id"], title="Issue-2", severity="medium")

    link_violated = client.post(
        f"{ISSUES_BASE}/{issue_1['id']}/policy-links",
        headers=org["org_headers"],
        json={"policy_id": policy["id"], "link_type": "violated"},
    )
    assert link_violated.status_code == 201
    assert link_violated.json()["link_type"] == "violated"

    link_related = client.post(
        f"{ISSUES_BASE}/{issue_2['id']}/policy-links",
        headers=org["org_headers"],
        json={"policy_id": policy["id"], "link_type": "related"},
    )
    assert link_related.status_code == 201
    assert link_related.json()["link_type"] == "related"

    duplicate = client.post(
        f"{ISSUES_BASE}/{issue_1['id']}/policy-links",
        headers=org["org_headers"],
        json={"policy_id": policy["id"], "link_type": "violated"},
    )
    assert duplicate.status_code == 409
    issue_row = db_session.query(Issue).filter(Issue.id == uuid.UUID(issue_1["id"])).one_or_none()
    assert issue_row is not None

    list_for_issue = client.get(f"{ISSUES_BASE}/{issue_1['id']}/policy-links", headers=org["org_headers"])
    assert list_for_issue.status_code == 200
    assert len(list_for_issue.json()) == 1

    associated_all = client.get(f"{POLICIES_BASE}/{policy['id']}/associated-issues", headers=org["org_headers"])
    assert associated_all.status_code == 200
    assert len(associated_all.json()) == 2

    associated_violated = client.get(
        f"{POLICIES_BASE}/{policy['id']}/associated-issues?link_type=violated",
        headers=org["org_headers"],
    )
    assert associated_violated.status_code == 200
    assert len(associated_violated.json()) == 1

    for idx in range(6):
        _create_issue(client, org["org_headers"], org["user_id"], title=f"Issue-extra-{idx}")

    issue_3 = _create_issue(client, org["org_headers"], org["user_id"], title="Issue-3")
    issue_4 = _create_issue(client, org["org_headers"], org["user_id"], title="Issue-4")

    for issue in [issue_3, issue_4]:
        resp = client.post(
            f"{ISSUES_BASE}/{issue['id']}/policy-links",
            headers=org["org_headers"],
            json={"policy_id": policy["id"], "link_type": "violated"},
        )
        assert resp.status_code == 201

    rate = client.get(f"{POLICIES_BASE}/{policy['id']}/violation-rate", headers=org["org_headers"])
    assert rate.status_code == 200
    assert rate.json()["total_issues_past_12m"] == 10
    assert rate.json()["violations_past_12m"] == 3
    assert rate.json()["violation_rate"] == 30.0

    policy_detail = client.get(f"{POLICIES_BASE}/{policy['id']}", headers=org["org_headers"])
    assert policy_detail.status_code == 200
    assert policy_detail.json()["violation_count"] == 3

    empty_policy = _create_policy(client, org_b["org_headers"], org_b["user_id"], title="No Issues")
    empty_rate = client.get(f"{POLICIES_BASE}/{empty_policy['id']}/violation-rate", headers=org_b["org_headers"])
    assert empty_rate.status_code == 200
    assert empty_rate.json()["violation_rate"] == 0.0

    unlink = client.delete(
        f"{ISSUES_BASE}/{issue_2['id']}/policy-links/{policy['id']}",
        headers=org["org_headers"],
    )
    assert unlink.status_code == 204

    removed = client.get(f"{ISSUES_BASE}/{issue_2['id']}/policy-links", headers=org["org_headers"])
    assert removed.status_code == 200
    assert removed.json() == []

    audit_log = db_session.query(AuditLog).filter(
        AuditLog.action == "issue_policy_link.removed",
        AuditLog.organization_id == uuid.UUID(org["organization_id"]),
    ).first()
    assert audit_log is not None

    cross_org = client.get(f"{ISSUES_BASE}/{issue_1['id']}/policy-links", headers=org_b["org_headers"])
    assert cross_org.status_code == 404


def test_a67_issue_control_linking_failure_rate_and_scoring_hook(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a67-main")
    org_b = bootstrap_org_user(client, email_prefix="a67-other")

    control = _create_control(client, org["org_headers"], title="Endpoint Protection")

    issue_failed = _create_issue(client, org["org_headers"], org["user_id"], title="Fail-1", severity="high")
    issue_absent = _create_issue(client, org["org_headers"], org["user_id"], title="Absent-1", severity="critical")

    link_failed = client.post(
        f"{ISSUES_BASE}/{issue_failed['id']}/control-links",
        headers=org["org_headers"],
        json={"control_id": control["id"], "failure_type": "control_failed"},
    )
    assert link_failed.status_code == 201

    link_absent = client.post(
        f"{ISSUES_BASE}/{issue_absent['id']}/control-links",
        headers=org["org_headers"],
        json={"control_id": control["id"], "failure_type": "control_absent"},
    )
    assert link_absent.status_code == 201

    duplicate = client.post(
        f"{ISSUES_BASE}/{issue_failed['id']}/control-links",
        headers=org["org_headers"],
        json={"control_id": control["id"], "failure_type": "control_failed"},
    )
    assert duplicate.status_code == 409

    grouped = client.get(f"{CONTROLS_BASE}/{control['id']}/associated-issues", headers=org["org_headers"])
    assert grouped.status_code == 200
    grouped_payload = grouped.json()["grouped"]
    assert len(grouped_payload["control_failed"]) == 1
    assert len(grouped_payload["control_absent"]) == 1

    extra_issue_ids: list[str] = []
    for idx in range(4):
        issue = _create_issue(client, org["org_headers"], org["user_id"], title=f"Extra-failure-{idx}", severity="medium")
        extra_issue_ids.append(issue["id"])
        resp = client.post(
            f"{ISSUES_BASE}/{issue['id']}/control-links",
            headers=org["org_headers"],
            json={"control_id": control["id"], "failure_type": "control_failed"},
        )
        assert resp.status_code == 201

    earliest_issue = db_session.query(Issue).filter(Issue.id == uuid.UUID(extra_issue_ids[-1])).one()
    earliest_issue.created_at = datetime.now(UTC) - timedelta(days=120)
    db_session.commit()

    failure_rate = client.get(f"{CONTROLS_BASE}/{control['id']}/failure-rate", headers=org["org_headers"])
    assert failure_rate.status_code == 200
    payload = failure_rate.json()
    assert payload["active_months"] == 5
    assert payload["total_failures"] == 5
    assert payload["failure_rate"] == 1.0
    assert payload["by_failure_type"]["control_absent"] == 1
    assert payload["open_high_critical_count"] == 2

    no_fail_control = _create_control(client, org["org_headers"], title="No Failures Control")
    no_fail_rate = client.get(f"{CONTROLS_BASE}/{no_fail_control['id']}/failure-rate", headers=org["org_headers"])
    assert no_fail_rate.status_code == 200
    assert no_fail_rate.json()["total_failures"] == 0
    assert no_fail_rate.json()["failure_rate"] == 0.0

    unlink = client.delete(
        f"{ISSUES_BASE}/{issue_absent['id']}/control-links/{control['id']}",
        headers=org["org_headers"],
    )
    assert unlink.status_code == 204

    scoring_payload = ScoringService(db_session).compute_control_health(uuid.UUID(org["organization_id"]))
    assert "score" in scoring_payload
    assert "inputs_json" in scoring_payload

    org_b_issue = _create_issue(client, org_b["org_headers"], org_b["user_id"], title="Other org issue")
    cross_org = client.get(f"{ISSUES_BASE}/{org_b_issue['id']}/control-links", headers=org["org_headers"])
    assert cross_org.status_code == 404
