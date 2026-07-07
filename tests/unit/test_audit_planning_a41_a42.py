from __future__ import annotations

from datetime import date, timedelta
import uuid

from app.compliance.services.pbc_service import PbcService
from app.core.security import get_password_hash
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user, login_user, org_headers

ENGAGEMENT_BASE = "/api/v1/compliance/audit-engagements"
PBC_BASE = "/api/v1/compliance/pbc-items"


def _create_active_user_with_role(db_session, org_id: str, email: str, role_name: str = "reviewer") -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0],
        hashed_password=get_password_hash("Pass1234!@"),
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    db_session.flush()

    role = db_session.query(Role).filter(Role.organization_id == uuid.UUID(org_id), Role.name == role_name).one()
    db_session.add(
        Membership(
            organization_id=uuid.UUID(org_id),
            user_id=user.id,
            role_id=role.id,
            status="active",
        )
    )
    db_session.commit()
    return user


def _framework_id(client, headers: dict[str, str]) -> str:
    resp = client.get("/api/v1/frameworks", headers=headers)
    assert resp.status_code == 200
    frameworks = resp.json()
    assert len(frameworks) > 0
    return frameworks[0]["id"]


def _create_engagement(
    client,
    headers: dict[str, str],
    *,
    framework_id: str,
    auditor_user_id: str,
    title: str = "SOC2 2026",
    audit_type: str = "external_certification",
    start_date_value: date | None = None,
    end_date_value: date | None = None,
) -> dict:
    resp = client.post(
        ENGAGEMENT_BASE,
        headers=headers,
        json={
            "title": title,
            "audit_type": audit_type,
            "scope_framework_ids": [framework_id],
            "assigned_auditor_ids": [auditor_user_id],
            "start_date": (start_date_value or (date.today() + timedelta(days=10))).isoformat(),
            "end_date": (end_date_value or (date.today() + timedelta(days=45))).isoformat(),
            "lead_auditor_name": "External Auditor",
            "audit_firm": "AuditCo",
            "notes": "Q3 engagement",
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _create_pbc_item(
    client,
    headers: dict[str, str],
    *,
    engagement_id: str,
    title: str = "Upload access review report",
    assignee_id: str | None = None,
    due_days: int = 7,
) -> dict:
    body = {
        "title": title,
        "description": "Provide auditor requested evidence",
        "due_date": (date.today() + timedelta(days=due_days)).isoformat(),
    }
    if assignee_id is not None:
        body["assignee_id"] = assignee_id

    resp = client.post(
        f"{PBC_BASE}?engagement_id={engagement_id}",
        headers=headers,
        json=body,
    )
    assert resp.status_code == 201
    return resp.json()


def _create_evidence(client, headers: dict[str, str], title: str) -> dict:
    resp = client.post(
        "/api/v1/evidence",
        headers=headers,
        json={"title": title, "evidence_type": "audit_report"},
    )
    assert resp.status_code == 201
    return resp.json()


def test_a41_create_engagement_valid_and_all_audit_types(client):
    org = bootstrap_org_user(client, email_prefix="a41-types")
    framework_id = _framework_id(client, org["headers"])

    for audit_type in ["internal_readiness", "external_certification", "surveillance", "gap_assessment"]:
        created = _create_engagement(
            client,
            org["org_headers"],
            framework_id=framework_id,
            auditor_user_id=org["user_id"],
            title=f"Engagement {audit_type}",
            audit_type=audit_type,
        )
        assert created["audit_type"] == audit_type
        assert created["status"] == "planning"


def test_a41_create_engagement_invalid_audit_type_returns_422(client):
    org = bootstrap_org_user(client, email_prefix="a41-invalid")
    framework_id = _framework_id(client, org["headers"])

    resp = client.post(
        ENGAGEMENT_BASE,
        headers=org["org_headers"],
        json={
            "title": "Bad engagement",
            "audit_type": "bad_type",
            "scope_framework_ids": [framework_id],
            "assigned_auditor_ids": [org["user_id"]],
            "start_date": (date.today() + timedelta(days=1)).isoformat(),
            "end_date": (date.today() + timedelta(days=2)).isoformat(),
        },
    )
    assert resp.status_code == 422


def test_a41_transition_valid_chain_and_report_issued_timestamp(client):
    org = bootstrap_org_user(client, email_prefix="a41-chain")
    framework_id = _framework_id(client, org["headers"])
    row = _create_engagement(client, org["org_headers"], framework_id=framework_id, auditor_user_id=org["user_id"])

    for next_status in ["fieldwork", "review", "report_issuance", "closed"]:
        moved = client.post(
            f"{ENGAGEMENT_BASE}/{row['id']}/transition",
            headers=org["org_headers"],
            json={"new_status": next_status},
        )
        assert moved.status_code == 200
        row = moved.json()
        assert row["status"] == next_status

    assert row["report_issued_at"] is not None


def test_a41_transition_invalid_returns_422(client):
    org = bootstrap_org_user(client, email_prefix="a41-bad-transition")
    framework_id = _framework_id(client, org["headers"])
    row = _create_engagement(client, org["org_headers"], framework_id=framework_id, auditor_user_id=org["user_id"])

    bad = client.post(
        f"{ENGAGEMENT_BASE}/{row['id']}/transition",
        headers=org["org_headers"],
        json={"new_status": "closed"},
    )
    assert bad.status_code == 422


def test_a41_soft_delete_allowed_from_planning_blocked_from_fieldwork(client):
    org = bootstrap_org_user(client, email_prefix="a41-delete")
    framework_id = _framework_id(client, org["headers"])

    planning = _create_engagement(
        client,
        org["org_headers"],
        framework_id=framework_id,
        auditor_user_id=org["user_id"],
        title="Delete planning",
    )
    allowed = client.delete(f"{ENGAGEMENT_BASE}/{planning['id']}", headers=org["org_headers"])
    assert allowed.status_code == 200

    fieldwork = _create_engagement(
        client,
        org["org_headers"],
        framework_id=framework_id,
        auditor_user_id=org["user_id"],
        title="Delete blocked",
    )
    moved = client.post(
        f"{ENGAGEMENT_BASE}/{fieldwork['id']}/transition",
        headers=org["org_headers"],
        json={"new_status": "fieldwork"},
    )
    assert moved.status_code == 200

    blocked = client.delete(f"{ENGAGEMENT_BASE}/{fieldwork['id']}", headers=org["org_headers"])
    assert blocked.status_code == 422


def test_a41_soft_delete_blocked_by_open_pbc_item_even_in_planning(client):
    org = bootstrap_org_user(client, email_prefix="a41-delete-openpbc")
    framework_id = _framework_id(client, org["headers"])

    engagement = _create_engagement(
        client,
        org["org_headers"],
        framework_id=framework_id,
        auditor_user_id=org["user_id"],
        title="Delete blocked by open PBC",
    )
    # PBC items can be requested before fieldwork starts, so an engagement can carry
    # open PBC work while still nominally in "planning" status.
    pbc_item = _create_pbc_item(client, org["org_headers"], engagement_id=engagement["id"])

    blocked = client.delete(f"{ENGAGEMENT_BASE}/{engagement['id']}", headers=org["org_headers"])
    assert blocked.status_code == 422
    assert "open PBC" in blocked.json()["detail"]

    reject = client.post(
        f"{PBC_BASE}/{pbc_item['id']}/reject",
        headers=org["org_headers"],
        json={"rejection_reason": "not needed"},
    )
    assert reject.status_code == 200

    # Rejected is still an open/actionable state (can be resubmitted), not terminal.
    still_blocked = client.delete(f"{ENGAGEMENT_BASE}/{engagement['id']}", headers=org["org_headers"])
    assert still_blocked.status_code == 422


def test_a41_dashboard_counts_and_org_isolation(client):
    org_a = bootstrap_org_user(client, email_prefix="a41-dash-a")
    org_b = bootstrap_org_user(client, email_prefix="a41-dash-b")
    framework_id = _framework_id(client, org_a["headers"])

    planning = _create_engagement(
        client,
        org_a["org_headers"],
        framework_id=framework_id,
        auditor_user_id=org_a["user_id"],
        title="Planning A",
        audit_type="internal_readiness",
    )
    review = _create_engagement(
        client,
        org_a["org_headers"],
        framework_id=framework_id,
        auditor_user_id=org_a["user_id"],
        title="Review A",
        audit_type="surveillance",
    )
    overdue = _create_engagement(
        client,
        org_a["org_headers"],
        framework_id=framework_id,
        auditor_user_id=org_a["user_id"],
        title="Overdue A",
        audit_type="gap_assessment",
        start_date_value=date.today() - timedelta(days=10),
        end_date_value=date.today() - timedelta(days=1),
    )
    _ = planning
    _ = overdue

    move_review = client.post(
        f"{ENGAGEMENT_BASE}/{review['id']}/transition",
        headers=org_a["org_headers"],
        json={"new_status": "fieldwork"},
    )
    assert move_review.status_code == 200
    move_review = client.post(
        f"{ENGAGEMENT_BASE}/{review['id']}/transition",
        headers=org_a["org_headers"],
        json={"new_status": "review"},
    )
    assert move_review.status_code == 200

    dashboard = client.get(f"{ENGAGEMENT_BASE}/dashboard", headers=org_a["org_headers"])
    assert dashboard.status_code == 200
    payload = dashboard.json()
    assert payload["total_engagements"] == 3
    assert payload["by_status"]["planning"] == 2
    assert payload["by_status"]["review"] == 1
    assert payload["by_type"]["internal_readiness"] == 1
    assert payload["by_type"]["surveillance"] == 1
    assert payload["overdue"] >= 1

    forbidden = client.get(f"{ENGAGEMENT_BASE}/{review['id']}", headers=org_b["org_headers"])
    assert forbidden.status_code == 404


def test_a42_create_submit_and_submit_with_evidence(client):
    org = bootstrap_org_user(client, email_prefix="a42-submit")
    framework_id = _framework_id(client, org["headers"])
    engagement = _create_engagement(client, org["org_headers"], framework_id=framework_id, auditor_user_id=org["user_id"])

    item = _create_pbc_item(client, org["org_headers"], engagement_id=engagement["id"], assignee_id=org["user_id"])

    submitted = client.post(
        f"{PBC_BASE}/{item['id']}/submit",
        headers=org["org_headers"],
        json={"evidence_id": None},
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "submitted"
    assert submitted.json()["submitted_at"] is not None

    item2 = _create_pbc_item(
        client,
        org["org_headers"],
        engagement_id=engagement["id"],
        assignee_id=org["user_id"],
        title="With evidence",
    )
    evidence = _create_evidence(client, org["org_headers"], title="PBC Evidence")
    submitted2 = client.post(
        f"{PBC_BASE}/{item2['id']}/submit",
        headers=org["org_headers"],
        json={"evidence_id": evidence["id"]},
    )
    assert submitted2.status_code == 200
    assert submitted2.json()["evidence_id"] == evidence["id"]


def test_a42_submit_wrong_org_evidence_returns_422(client):
    org_a = bootstrap_org_user(client, email_prefix="a42-ev-a")
    org_b = bootstrap_org_user(client, email_prefix="a42-ev-b")

    framework_id = _framework_id(client, org_a["headers"])
    engagement = _create_engagement(client, org_a["org_headers"], framework_id=framework_id, auditor_user_id=org_a["user_id"])
    item = _create_pbc_item(client, org_a["org_headers"], engagement_id=engagement["id"], assignee_id=org_a["user_id"])
    evidence_b = _create_evidence(client, org_b["org_headers"], title="Wrong org evidence")

    bad = client.post(
        f"{PBC_BASE}/{item['id']}/submit",
        headers=org_a["org_headers"],
        json={"evidence_id": evidence_b["id"]},
    )
    assert bad.status_code == 422


def test_a42_accept_reject_permissions_and_status(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a42-accept")
    framework_id = _framework_id(client, org["headers"])
    engagement = _create_engagement(client, org["org_headers"], framework_id=framework_id, auditor_user_id=org["user_id"])

    reviewer = _create_active_user_with_role(db_session, org["organization_id"], "a42-reviewer@example.com", "reviewer")
    reviewer_headers = org_headers(login_user(client, reviewer.email), org["organization_id"])

    item = _create_pbc_item(client, org["org_headers"], engagement_id=engagement["id"], assignee_id=org["user_id"])
    submit = client.post(
        f"{PBC_BASE}/{item['id']}/submit",
        headers=org["org_headers"],
        json={"evidence_id": None},
    )
    assert submit.status_code == 200

    non_requester_accept = client.post(f"{PBC_BASE}/{item['id']}/accept", headers=reviewer_headers)
    assert non_requester_accept.status_code == 403

    accepted = client.post(f"{PBC_BASE}/{item['id']}/accept", headers=org["org_headers"])
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"
    assert accepted.json()["accepted_at"] is not None

    item2 = _create_pbc_item(client, org["org_headers"], engagement_id=engagement["id"], assignee_id=org["user_id"], title="reject me")
    reject_non_requester = client.post(
        f"{PBC_BASE}/{item2['id']}/reject",
        headers=reviewer_headers,
        json={"rejection_reason": "no"},
    )
    assert reject_non_requester.status_code == 403

    rejected = client.post(
        f"{PBC_BASE}/{item2['id']}/reject",
        headers=org["org_headers"],
        json={"rejection_reason": "Need revision"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["rejection_reason"] == "Need revision"


def test_a42_mark_overdue_summary_and_soft_delete_rules(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a42-overdue")
    framework_id = _framework_id(client, org["headers"])
    engagement = _create_engagement(client, org["org_headers"], framework_id=framework_id, auditor_user_id=org["user_id"])

    old_pending = _create_pbc_item(
        client,
        org["org_headers"],
        engagement_id=engagement["id"],
        title="old",
        assignee_id=org["user_id"],
        due_days=-3,
    )
    accepted_item = _create_pbc_item(
        client,
        org["org_headers"],
        engagement_id=engagement["id"],
        title="accepted",
        assignee_id=org["user_id"],
        due_days=2,
    )
    pending_delete = _create_pbc_item(
        client,
        org["org_headers"],
        engagement_id=engagement["id"],
        title="delete pending",
        assignee_id=org["user_id"],
        due_days=2,
    )

    submit = client.post(
        f"{PBC_BASE}/{accepted_item['id']}/submit",
        headers=org["org_headers"],
        json={"evidence_id": None},
    )
    assert submit.status_code == 200
    accept = client.post(f"{PBC_BASE}/{accepted_item['id']}/accept", headers=org["org_headers"])
    assert accept.status_code == 200

    service = PbcService(db_session)
    marked = service.mark_overdue_items(uuid.UUID(org["organization_id"]))
    db_session.commit()
    assert marked >= 1

    refreshed = client.get(f"{PBC_BASE}/{old_pending['id']}", headers=org["org_headers"])
    assert refreshed.status_code == 200
    assert refreshed.json()["status"] == "overdue"

    summary = client.get(f"{PBC_BASE}/engagement/{engagement['id']}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_items"] == 3
    assert body["by_status"]["accepted"] == 1
    assert body["completion_rate"] == round((1 / 3) * 100, 2)

    blocked_delete = client.delete(f"{PBC_BASE}/{accepted_item['id']}", headers=org["org_headers"])
    assert blocked_delete.status_code == 422

    allowed_delete = client.delete(f"{PBC_BASE}/{pending_delete['id']}", headers=org["org_headers"])
    assert allowed_delete.status_code == 200


def test_a42_pbc_item_overdue_relative_to_fieldwork_deadline(client):
    """Regression: a PBC item's own due_date isn't what actually matters to an auditor --
    what matters is whether it will be resolved before the *engagement's* fieldwork
    deadline (end_date). An item can be "not overdue" by its own due_date yet already
    past the point where the audit itself can still use it. Both signals, plus exactly
    how many days overdue against each, must be surfaced."""
    org = bootstrap_org_user(client, email_prefix="a42-fieldwork-deadline")
    framework_id = _framework_id(client, org["headers"])

    # Engagement whose fieldwork window has already closed.
    past_engagement = _create_engagement(
        client,
        org["org_headers"],
        framework_id=framework_id,
        auditor_user_id=org["user_id"],
        title="Past fieldwork",
        start_date_value=date.today() - timedelta(days=20),
        end_date_value=date.today() - timedelta(days=5),
    )
    # Item's own due_date is still in the future -- not overdue by its own date.
    item = _create_pbc_item(
        client,
        org["org_headers"],
        engagement_id=past_engagement["id"],
        title="Still-open item past fieldwork deadline",
        due_days=5,
    )
    assert item["days_overdue"] == 0
    assert item["fieldwork_deadline"] == past_engagement["end_date"]
    assert item["overdue_relative_to_fieldwork_deadline"] is True
    assert item["days_past_fieldwork_deadline"] == 5

    detail = client.get(f"{PBC_BASE}/{item['id']}", headers=org["org_headers"])
    assert detail.status_code == 200
    assert detail.json()["overdue_relative_to_fieldwork_deadline"] is True

    listed = client.get(PBC_BASE, headers=org["org_headers"], params={"engagement_id": past_engagement["id"]})
    assert listed.status_code == 200
    listed_item = next(row for row in listed.json() if row["id"] == item["id"])
    assert listed_item["overdue_relative_to_fieldwork_deadline"] is True
    assert listed_item["days_past_fieldwork_deadline"] == 5

    # A currently-active engagement's fieldwork deadline is still ahead -- no flag.
    active_engagement = _create_engagement(
        client,
        org["org_headers"],
        framework_id=framework_id,
        auditor_user_id=org["user_id"],
        title="Active fieldwork",
    )
    active_item = _create_pbc_item(
        client,
        org["org_headers"],
        engagement_id=active_engagement["id"],
        title="On track item",
        due_days=5,
    )
    assert active_item["overdue_relative_to_fieldwork_deadline"] is False
    assert active_item["days_past_fieldwork_deadline"] == 0

    # Accepting an item resolves it -- it's no longer "at risk" even past deadline.
    accept_resp = client.post(
        f"{PBC_BASE}/{item['id']}/submit",
        headers=org["org_headers"],
        json={"evidence_id": None},
    )
    assert accept_resp.status_code == 200
    accepted = client.post(f"{PBC_BASE}/{item['id']}/accept", headers=org["org_headers"])
    assert accepted.status_code == 200
    assert accepted.json()["overdue_relative_to_fieldwork_deadline"] is False
