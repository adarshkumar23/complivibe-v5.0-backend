"""Regression tests for the control-exception approval-chain collapse (2026-07-20).

Before the fix, the approve endpoint required exceptions:approve AND the service
derived its "override authority" from that same permission. Every caller who could
reach the endpoint therefore held override, so the per-step assigned-approver guard
and (absent) distinct-identity guard were dead code: one identity could approve
every step of a multi-step chain and drive the exception straight to active.

The fix:
  * the endpoint gate is now org membership, not exceptions:approve;
  * override is a distinct, rarely-granted permission (exceptions:override, owner/
    admin only), so exceptions:approve holders (e.g. reviewer) are ordinary
    approvers bound by the chain;
  * the per-step guard is therefore live for ordinary approvers; and
  * a distinct-identity guard rejects an approver who already cleared another step
    of the same chain, absent override.

Reviewers are used as the "ordinary approver" identity throughout: reviewer holds
exceptions:approve (so it could reach the endpoint on the pre-fix code) but not
exceptions:override (so post-fix it is bound by the chain). That makes these tests
flip cleanly against the pre-fix source.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from app.core.security import get_password_hash
from app.models.control_exception import ControlException
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user, login_user, org_headers

pytestmark = pytest.mark.usefixtures("seeded_reference_data")

BASE = "/api/v1/compliance/control-exceptions"


def _member_headers(db_session, client, org_id: str, email: str, role_name: str) -> tuple[User, dict[str, str]]:
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
        Membership(organization_id=uuid.UUID(org_id), user_id=user.id, role_id=role.id, status="active")
    )
    db_session.commit()
    return user, org_headers(login_user(client, email), org_id)


def _create_control(client, headers: dict[str, str], title: str) -> dict:
    resp = client.post(
        "/api/v1/controls",
        headers=headers,
        json={"title": title, "control_type": "policy", "criticality": "medium"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_exception(client, headers, *, control_id, owner_user_id, approvers=None) -> dict:
    payload = {
        "control_id": control_id,
        "title": "Exception Request",
        "description": "Cannot meet control temporarily",
        "exception_type": "temporary",
        "risk_acceptance_reason": "Business continuity window",
        "owner_user_id": owner_user_id,
        "effective_date": (date.today() - timedelta(days=1)).isoformat(),
        "expiry_date": (date.today() + timedelta(days=30)).isoformat(),
    }
    if approvers is not None:
        payload["approvers"] = approvers
    resp = client.post(BASE, headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _status(db_session, exception_id: str) -> str:
    row = db_session.execute(
        ControlException.__table__.select().where(ControlException.id == uuid.UUID(exception_id))
    ).first()
    return row.status


def test_endpoint_gate_is_membership_not_exceptions_approve(client, db_session):
    """An assigned approver WITHOUT exceptions:approve can now reach approve().

    Pre-fix the endpoint required exceptions:approve, so a compliance_manager
    (which lacks it) got 403 and could never clear even their own assigned step.
    """
    org = bootstrap_org_user(client, email_prefix="cc-gate")
    owner_headers = org["org_headers"]
    cm, cm_headers = _member_headers(db_session, client, org["organization_id"], "cc-gate-cm@example.com", "compliance_manager")

    control = _create_control(client, owner_headers, "Gate Control")
    exc = _create_exception(
        client,
        owner_headers,
        control_id=control["id"],
        owner_user_id=str(cm.id),
        approvers=[{"user_id": str(cm.id), "sequence": 1}],
    )

    resp = client.post(f"{BASE}/{exc['id']}/approve", headers=cm_headers, json={"decision_notes": "own step"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "active"


def test_single_identity_cannot_collapse_three_distinct_approver_chain(client, db_session):
    """THE PROOF: a 3-step chain naming 3 distinct approvers cannot be satisfied
    by one non-requester identity calling approve() three times."""
    org = bootstrap_org_user(client, email_prefix="cc-collapse")
    owner_headers = org["org_headers"]

    a, a_headers = _member_headers(db_session, client, org["organization_id"], "cc-a@example.com", "reviewer")
    b, _ = _member_headers(db_session, client, org["organization_id"], "cc-b@example.com", "reviewer")
    c, _ = _member_headers(db_session, client, org["organization_id"], "cc-c@example.com", "reviewer")

    control = _create_control(client, owner_headers, "Collapse Control")
    exc = _create_exception(
        client,
        owner_headers,
        control_id=control["id"],
        owner_user_id=str(a.id),
        approvers=[
            {"user_id": str(a.id), "sequence": 1},
            {"user_id": str(b.id), "sequence": 2},
            {"user_id": str(c.id), "sequence": 3},
        ],
    )

    # Call 1: A clears its own assigned step -> partial, still pending.
    r1 = client.post(f"{BASE}/{exc['id']}/approve", headers=a_headers, json={"decision_notes": "1"})
    assert r1.status_code == 200, r1.text
    assert r1.json()["status"] == "pending_approval"

    # Call 2: A tries again -> rejected (already decided a step / not the current
    # step's assigned approver). This is where the pre-fix collapse happened.
    r2 = client.post(f"{BASE}/{exc['id']}/approve", headers=a_headers, json={"decision_notes": "2"})
    assert r2.status_code == 422, r2.text

    # Call 3: A tries a third time -> still rejected.
    r3 = client.post(f"{BASE}/{exc['id']}/approve", headers=a_headers, json={"decision_notes": "3"})
    assert r3.status_code == 422, r3.text

    # The exception was NEVER activated by A alone.
    assert _status(db_session, exc["id"]) == "pending_approval"
    detail = client.get(f"{BASE}/{exc['id']}", headers=owner_headers).json()
    step_status = {s["sequence"]: s["status"] for s in detail["approvals"]}
    assert step_status == {1: "approved", 2: "pending", 3: "pending"}


def test_same_approver_assigned_twice_blocked_by_distinct_identity(client, db_session):
    """A person assigned to two steps may still only clear one (four-eyes)."""
    org = bootstrap_org_user(client, email_prefix="cc-dupe")
    owner_headers = org["org_headers"]

    a, a_headers = _member_headers(db_session, client, org["organization_id"], "cc-dupe-a@example.com", "reviewer")
    b, _ = _member_headers(db_session, client, org["organization_id"], "cc-dupe-b@example.com", "reviewer")

    control = _create_control(client, owner_headers, "Dupe Control")
    exc = _create_exception(
        client,
        owner_headers,
        control_id=control["id"],
        owner_user_id=str(a.id),
        approvers=[
            {"user_id": str(a.id), "sequence": 1},
            {"user_id": str(a.id), "sequence": 2},
            {"user_id": str(b.id), "sequence": 3},
        ],
    )

    r1 = client.post(f"{BASE}/{exc['id']}/approve", headers=a_headers, json={"decision_notes": "1"})
    assert r1.status_code == 200, r1.text

    r2 = client.post(f"{BASE}/{exc['id']}/approve", headers=a_headers, json={"decision_notes": "2"})
    assert r2.status_code == 422, r2.text
    assert "already approved" in r2.json()["detail"].lower()
    assert _status(db_session, exc["id"]) == "pending_approval"


def test_three_distinct_approvers_happy_path_activates(client, db_session):
    """No over-correction: three distinct approvers clearing their own steps in
    order activates the exception."""
    org = bootstrap_org_user(client, email_prefix="cc-happy")
    owner_headers = org["org_headers"]

    a, a_headers = _member_headers(db_session, client, org["organization_id"], "cc-h-a@example.com", "reviewer")
    b, b_headers = _member_headers(db_session, client, org["organization_id"], "cc-h-b@example.com", "reviewer")
    c, c_headers = _member_headers(db_session, client, org["organization_id"], "cc-h-c@example.com", "reviewer")

    control = _create_control(client, owner_headers, "Happy Control")
    exc = _create_exception(
        client,
        owner_headers,
        control_id=control["id"],
        owner_user_id=str(a.id),
        approvers=[
            {"user_id": str(a.id), "sequence": 1},
            {"user_id": str(b.id), "sequence": 2},
            {"user_id": str(c.id), "sequence": 3},
        ],
    )

    assert client.post(f"{BASE}/{exc['id']}/approve", headers=a_headers, json={"decision_notes": "a"}).status_code == 200
    assert client.post(f"{BASE}/{exc['id']}/approve", headers=b_headers, json={"decision_notes": "b"}).status_code == 200
    last = client.post(f"{BASE}/{exc['id']}/approve", headers=c_headers, json={"decision_notes": "c"})
    assert last.status_code == 200, last.text
    assert last.json()["status"] == "active"
    assert last.json()["approved_by_user_id"] == str(c.id)


def test_override_holder_may_clear_whole_chain(client, db_session):
    """Break-glass preserved: an exceptions:override holder (admin) may clear every
    step of a chain naming other approvers."""
    org = bootstrap_org_user(client, email_prefix="cc-ovr")
    owner_headers = org["org_headers"]

    admin, admin_headers = _member_headers(db_session, client, org["organization_id"], "cc-ovr-admin@example.com", "admin")
    b, _ = _member_headers(db_session, client, org["organization_id"], "cc-ovr-b@example.com", "reviewer")
    c, _ = _member_headers(db_session, client, org["organization_id"], "cc-ovr-c@example.com", "reviewer")

    control = _create_control(client, owner_headers, "Override Control")
    exc = _create_exception(
        client,
        owner_headers,
        control_id=control["id"],
        owner_user_id=str(b.id),
        approvers=[
            {"user_id": str(b.id), "sequence": 1},
            {"user_id": str(c.id), "sequence": 2},
        ],
    )

    assert client.post(f"{BASE}/{exc['id']}/approve", headers=admin_headers, json={"decision_notes": "1"}).status_code == 200
    final = client.post(f"{BASE}/{exc['id']}/approve", headers=admin_headers, json={"decision_notes": "2"})
    assert final.status_code == 200, final.text
    assert final.json()["status"] == "active"


def test_chainless_approval_requires_exceptions_approve(client, db_session):
    """A chainless exception (no four-eyes intent) is a single-approver decision:
    it needs exceptions:approve, not override. A bare member who can now reach the
    membership-gated endpoint but lacks exceptions:approve cannot activate it; a
    reviewer (holds exceptions:approve) and an admin can."""
    org = bootstrap_org_user(client, email_prefix="cc-chainless")
    owner_headers = org["org_headers"]

    cm, cm_headers = _member_headers(db_session, client, org["organization_id"], "cc-cl-cm@example.com", "compliance_manager")
    reviewer, reviewer_headers = _member_headers(db_session, client, org["organization_id"], "cc-cl-rev@example.com", "reviewer")
    admin, admin_headers = _member_headers(db_session, client, org["organization_id"], "cc-cl-admin@example.com", "admin")

    control = _create_control(client, owner_headers, "Chainless Control")

    # compliance_manager lacks exceptions:approve -> rejected on the chainless path.
    exc0 = _create_exception(client, owner_headers, control_id=control["id"], owner_user_id=str(cm.id))
    cm_resp = client.post(f"{BASE}/{exc0['id']}/approve", headers=cm_headers, json={"decision_notes": "x"})
    assert cm_resp.status_code == 422, cm_resp.text
    assert _status(db_session, exc0["id"]) == "pending_approval"

    # reviewer holds exceptions:approve -> the pre-fix chainless workflow is preserved.
    exc1 = _create_exception(client, owner_headers, control_id=control["id"], owner_user_id=str(reviewer.id))
    rev = client.post(f"{BASE}/{exc1['id']}/approve", headers=reviewer_headers, json={"decision_notes": "ok"})
    assert rev.status_code == 200, rev.text
    assert rev.json()["status"] == "active"

    exc2 = _create_exception(client, owner_headers, control_id=control["id"], owner_user_id=str(admin.id))
    adm = client.post(f"{BASE}/{exc2['id']}/approve", headers=admin_headers, json={"decision_notes": "ok"})
    assert adm.status_code == 200, adm.text
    assert adm.json()["status"] == "active"
