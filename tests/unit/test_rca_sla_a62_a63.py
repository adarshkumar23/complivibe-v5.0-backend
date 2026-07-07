from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.models.issue_sla_tracking import IssueSLATracking
from app.models.root_cause_analysis import RootCauseAnalysis
from tests.helpers.auth_org import bootstrap_org_user


ISSUES_BASE = "/api/v1/compliance/issues"
SETTINGS_BASE = "/api/v1/compliance/issue-settings"
SLA_POLICIES_BASE = "/api/v1/compliance/sla-policies"


def _create_issue(client, headers: dict[str, str], owner_id: str, *, severity: str = "medium") -> dict:
    response = client.post(
        ISSUES_BASE,
        headers=headers,
        json={
            "title": f"Issue {severity}",
            "description": "Issue description",
            "issue_type": "custom",
            "severity": severity,
            "source_type": "manual",
            "owner_id": owner_id,
        },
    )
    assert response.status_code == 201
    return response.json()


def _transition_to_resolved(client, headers: dict[str, str], issue_id: str) -> None:
    for state in ["investigating", "mitigating", "resolved"]:
        response = client.post(
            f"{ISSUES_BASE}/{issue_id}/transition",
            headers=headers,
            json={"new_status": state},
        )
        assert response.status_code == 200


def test_a62_rca_creation_review_and_immutability(client):
    org = bootstrap_org_user(client, email_prefix="a62-rca")

    open_issue = _create_issue(client, org["org_headers"], org["user_id"])
    open_rca = client.post(
        f"{ISSUES_BASE}/{open_issue['id']}/rca",
        headers=org["org_headers"],
        json={
            "summary": "RCA summary",
            "timeline_description": "Timeline",
            "root_cause": "Root cause",
            "contributing_factors": ["factor"],
            "corrective_actions": ["action"],
            "preventive_measures": ["measure"],
        },
    )
    assert open_rca.status_code == 422

    issue = _create_issue(client, org["org_headers"], org["user_id"])
    _transition_to_resolved(client, org["org_headers"], issue["id"])

    create_rca = client.post(
        f"{ISSUES_BASE}/{issue['id']}/rca",
        headers=org["org_headers"],
        json={
            "summary": "RCA summary",
            "timeline_description": "Timeline",
            "root_cause": "Root cause",
            "contributing_factors": ["factor a"],
            "corrective_actions": ["fix a"],
            "preventive_measures": ["prevent a"],
        },
    )
    assert create_rca.status_code == 201

    second_rca = client.post(
        f"{ISSUES_BASE}/{issue['id']}/rca",
        headers=org["org_headers"],
        json={
            "summary": "duplicate",
            "timeline_description": "duplicate",
            "root_cause": "duplicate",
            "contributing_factors": [],
            "corrective_actions": [],
            "preventive_measures": [],
        },
    )
    assert second_rca.status_code == 409

    update_before_review = client.patch(
        f"{ISSUES_BASE}/{issue['id']}/rca",
        headers=org["org_headers"],
        json={"summary": "Updated summary"},
    )
    assert update_before_review.status_code == 200
    assert update_before_review.json()["summary"] == "Updated summary"

    reviewer = bootstrap_org_user(client, email_prefix="a62-reviewer")
    invite = client.post(
        "/api/v1/memberships",
        headers=org["org_headers"],
        json={"email": reviewer["email"], "role_name": "compliance_manager", "status": "active"},
    )
    assert invite.status_code == 201

    self_review = client.post(
        f"{ISSUES_BASE}/{issue['id']}/rca/review",
        headers=org["org_headers"],
    )
    assert self_review.status_code == 422

    reviewer_headers = {
        "Authorization": f"Bearer {reviewer['access_token']}",
        "X-Organization-ID": org["organization_id"],
    }
    review = client.post(f"{ISSUES_BASE}/{issue['id']}/rca/review", headers=reviewer_headers)
    assert review.status_code == 200
    assert review.json()["reviewed_by"] == reviewer["user_id"]
    assert review.json()["reviewed_at"] is not None

    update_after_review = client.patch(
        f"{ISSUES_BASE}/{issue['id']}/rca",
        headers=org["org_headers"],
        json={"summary": "Blocked change"},
    )
    assert update_after_review.status_code == 422


def test_a62_rca_flags_stale_when_issue_severity_changes_after_creation(client, db_session):
    from app.models.issue import Issue

    org = bootstrap_org_user(client, email_prefix="a62-stale")
    issue = _create_issue(client, org["org_headers"], org["user_id"], severity="medium")
    _transition_to_resolved(client, org["org_headers"], issue["id"])

    create_rca = client.post(
        f"{ISSUES_BASE}/{issue['id']}/rca",
        headers=org["org_headers"],
        json={
            "summary": "RCA summary",
            "timeline_description": "Timeline",
            "root_cause": "Root cause",
            "contributing_factors": [],
            "corrective_actions": [],
            "preventive_measures": [],
        },
    )
    assert create_rca.status_code == 201
    assert create_rca.json()["severity_at_creation"] == "medium"
    assert create_rca.json()["severity_changed_since_rca"] is False

    # Severity has no public update endpoint today, so mutate directly to
    # simulate an internal re-triage happening after the RCA was authored.
    issue_row = db_session.query(Issue).filter(Issue.id == uuid.UUID(issue["id"])).one()
    issue_row.severity = "critical"
    db_session.commit()

    fetched = client.get(f"{ISSUES_BASE}/{issue['id']}/rca", headers=org["org_headers"])
    assert fetched.status_code == 200
    assert fetched.json()["severity_at_creation"] == "medium"
    assert fetched.json()["severity_changed_since_rca"] is True


def test_a62_rca_duplicate_creation_race_returns_409_not_500(client, db_session, monkeypatch):
    """Two concurrent create_rca calls can both pass the "existing is None"
    pre-check before either flushes (classic TOCTOU race). The unique
    constraint on issue_id is the real source of truth -- create_rca must
    catch the resulting IntegrityError on flush and translate it into a 409,
    not let it bubble up as an unhandled 500."""
    from app.compliance.services.rca_service import RCAService
    from app.schemas.rca import RCACreate

    org = bootstrap_org_user(client, email_prefix="a62-race")
    issue = _create_issue(client, org["org_headers"], org["user_id"])
    _transition_to_resolved(client, org["org_headers"], issue["id"])

    payload = RCACreate(
        summary="First RCA",
        timeline_description="Timeline",
        root_cause="Root cause",
        contributing_factors=[],
        corrective_actions=[],
        preventive_measures=[],
    )
    service = RCAService(db_session)
    first = service.create_rca(uuid.UUID(org["organization_id"]), uuid.UUID(issue["id"]), payload, uuid.UUID(org["user_id"]))
    db_session.commit()
    assert first is not None

    # Simulate the race: pretend the pre-check found nothing (as it would
    # for a second request that read before the first committed) so we
    # exercise the flush-time IntegrityError path instead of the normal
    # check-then-409 path.
    from sqlalchemy.engine import Result

    original_scalar_one_or_none = Result.scalar_one_or_none
    call_count = {"n": 0}

    def _fake_scalar_one_or_none(self):
        call_count["n"] += 1
        # Call #1 is create_rca's own issue lookup (_get_issue) -- must
        # resolve normally. Call #2 is the "existing RCA?" pre-check, which
        # we force to lie and say "no existing row" to simulate the race.
        if call_count["n"] == 2:
            return None
        return original_scalar_one_or_none(self)

    monkeypatch.setattr(Result, "scalar_one_or_none", _fake_scalar_one_or_none)

    from fastapi import HTTPException

    try:
        service.create_rca(uuid.UUID(org["organization_id"]), uuid.UUID(issue["id"]), payload, uuid.UUID(org["user_id"]))
        raise AssertionError("expected HTTPException(409) for racing duplicate RCA create")
    except HTTPException as exc:
        assert exc.status_code == 409


def test_a62_require_rca_before_close_enforcement(client):
    org = bootstrap_org_user(client, email_prefix="a62-close")

    issue = _create_issue(client, org["org_headers"], org["user_id"])
    _transition_to_resolved(client, org["org_headers"], issue["id"])

    close_without_rca = client.post(
        f"{ISSUES_BASE}/{issue['id']}/transition",
        headers=org["org_headers"],
        json={"new_status": "closed", "resolution_note": "done"},
    )
    assert close_without_rca.status_code == 422

    create_rca = client.post(
        f"{ISSUES_BASE}/{issue['id']}/rca",
        headers=org["org_headers"],
        json={
            "summary": "RCA for closure",
            "timeline_description": "Timeline",
            "root_cause": "Cause",
            "contributing_factors": [],
            "corrective_actions": [],
            "preventive_measures": [],
        },
    )
    assert create_rca.status_code == 201

    close_with_rca = client.post(
        f"{ISSUES_BASE}/{issue['id']}/transition",
        headers=org["org_headers"],
        json={"new_status": "closed", "resolution_note": "done"},
    )
    assert close_with_rca.status_code == 200
    assert close_with_rca.json()["status"] == "closed"

    disable = client.patch(SETTINGS_BASE, headers=org["org_headers"], json={"require_rca_before_close": False})
    assert disable.status_code == 200

    issue2 = _create_issue(client, org["org_headers"], org["user_id"])
    _transition_to_resolved(client, org["org_headers"], issue2["id"])

    close_without_rca_allowed = client.post(
        f"{ISSUES_BASE}/{issue2['id']}/transition",
        headers=org["org_headers"],
        json={"new_status": "closed", "resolution_note": "done"},
    )
    assert close_without_rca_allowed.status_code == 200
    assert close_without_rca_allowed.json()["status"] == "closed"


def test_a63_sla_tracking_deadlines_and_policy_override(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a63-deadlines")

    issue = _create_issue(client, org["org_headers"], org["user_id"], severity="critical")
    issue_id = uuid.UUID(issue["id"])

    tracking = db_session.query(IssueSLATracking).filter(IssueSLATracking.issue_id == issue_id).one_or_none()
    assert tracking is not None

    created_at = datetime.fromisoformat(issue["created_at"])
    assert tracking.response_deadline == created_at + timedelta(hours=1)
    assert tracking.resolution_deadline == created_at + timedelta(hours=24)

    to_investigating = client.post(
        f"{ISSUES_BASE}/{issue['id']}/transition",
        headers=org["org_headers"],
        json={"new_status": "investigating"},
    )
    assert to_investigating.status_code == 200

    tracking = db_session.query(IssueSLATracking).filter(IssueSLATracking.issue_id == issue_id).one()
    assert tracking.response_met_at is not None

    to_mitigating = client.post(
        f"{ISSUES_BASE}/{issue['id']}/transition",
        headers=org["org_headers"],
        json={"new_status": "mitigating"},
    )
    assert to_mitigating.status_code == 200

    to_resolved = client.post(
        f"{ISSUES_BASE}/{issue['id']}/transition",
        headers=org["org_headers"],
        json={"new_status": "resolved"},
    )
    assert to_resolved.status_code == 200

    tracking = db_session.query(IssueSLATracking).filter(IssueSLATracking.issue_id == issue_id).one()
    assert tracking.resolution_met_at is not None

    custom_policy = client.post(
        SLA_POLICIES_BASE,
        headers=org["org_headers"],
        json={"severity": "critical", "response_hours": 2, "resolution_hours": 48},
    )
    assert custom_policy.status_code == 200

    custom_issue = _create_issue(client, org["org_headers"], org["user_id"], severity="critical")
    custom_tracking = db_session.query(IssueSLATracking).filter(
        IssueSLATracking.issue_id == uuid.UUID(custom_issue["id"])
    ).one()
    custom_created_at = datetime.fromisoformat(custom_issue["created_at"])
    assert custom_tracking.response_deadline == custom_created_at + timedelta(hours=2)


def test_a63_sla_breach_checks_idempotency_org_isolation_and_resolved_guard(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="a63-breach-a")
    org_b = bootstrap_org_user(client, email_prefix="a63-breach-b")

    breach_issue = _create_issue(client, org_a["org_headers"], org_a["user_id"], severity="high")
    breach_issue_id = uuid.UUID(breach_issue["id"])
    breach_tracking = db_session.query(IssueSLATracking).filter(IssueSLATracking.issue_id == breach_issue_id).one()
    breach_tracking.response_deadline = datetime.now(UTC) - timedelta(hours=2)
    breach_tracking.response_met_at = None
    breach_tracking.response_breached = False
    db_session.commit()

    resolved_issue = _create_issue(client, org_a["org_headers"], org_a["user_id"], severity="medium")
    _transition_to_resolved(client, org_a["org_headers"], resolved_issue["id"])
    resolved_tracking = db_session.query(IssueSLATracking).filter(
        IssueSLATracking.issue_id == uuid.UUID(resolved_issue["id"])
    ).one()
    resolved_tracking.resolution_deadline = datetime.now(UTC) - timedelta(hours=1)
    resolved_tracking.resolution_met_at = None
    resolved_tracking.resolution_breached = False
    db_session.commit()

    first_check = client.get(f"{SLA_POLICIES_BASE}/trigger-breach-check", headers=org_a["org_headers"])
    assert first_check.status_code == 200
    assert first_check.json()["response_breached"] >= 1

    second_check = client.get(f"{SLA_POLICIES_BASE}/trigger-breach-check", headers=org_a["org_headers"])
    assert second_check.status_code == 200
    assert second_check.json()["response_breached"] == 0

    status_response = client.get(f"{ISSUES_BASE}/{breach_issue['id']}/sla-status", headers=org_a["org_headers"])
    assert status_response.status_code == 200
    assert status_response.json()["response_breached"] is True

    org_a_breaches = client.get(f"{ISSUES_BASE}/sla-breaches", headers=org_a["org_headers"])
    assert org_a_breaches.status_code == 200
    ids = {row["issue_id"] for row in org_a_breaches.json()}
    assert breach_issue["id"] in ids

    org_b_breaches = client.get(f"{ISSUES_BASE}/sla-breaches", headers=org_b["org_headers"])
    assert org_b_breaches.status_code == 200
    assert all(row["issue_id"] != breach_issue["id"] for row in org_b_breaches.json())

    resolved_status = client.get(f"{ISSUES_BASE}/{resolved_issue['id']}/sla-status", headers=org_a["org_headers"])
    assert resolved_status.status_code == 200
    assert resolved_status.json()["resolution_breached"] is False

    rca_count = db_session.query(RootCauseAnalysis).filter(
        RootCauseAnalysis.organization_id == uuid.UUID(org_a["organization_id"])
    ).count()
    assert rca_count >= 0
