"""Coverage for the audit-engagements endpoints
(/compliance/audit-engagements). Zero prior test references.

Covers create/list/get/transition happy path (asserting real fields),
audit:write permission enforcement, and edge cases (invalid status
transition 422, 404 for a missing engagement, org-scoping isolation).
"""

from __future__ import annotations

import uuid

from tests.helpers.auth_org import add_org_member, bootstrap_org_user

BASE = "/api/v1/compliance/audit-engagements"


def _create_body(**over) -> dict:
    body = {
        "title": "SOC 2 Type II readiness",
        "audit_type": "internal_readiness",
        "start_date": "2027-01-01",
        "end_date": "2027-03-01",
    }
    body.update(over)
    return body


def _create(client, headers, **over) -> dict:
    r = client.post(BASE, headers=headers, json=_create_body(**over))
    assert r.status_code == 201, r.text
    return r.json()


def test_create_list_get_transition_happy_path(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ae-happy")
    h, oid = org["org_headers"], org["organization_id"]

    created = _create(client, h)
    assert created["title"] == "SOC 2 Type II readiness"
    assert created["audit_type"] == "internal_readiness"
    assert created["status"] == "planning"
    assert created["start_date"] == "2027-01-01"
    assert created["end_date"] == "2027-03-01"
    assert created["organization_id"] == oid
    assert created["created_by"] == org["user_id"]
    eid = created["id"]

    # list (org-scoped) contains it
    listed = client.get(BASE, headers=h)
    assert listed.status_code == 200, listed.text
    assert any(row["id"] == eid for row in listed.json())

    # list with audit_type filter
    filtered = client.get(f"{BASE}?audit_type=internal_readiness", headers=h)
    assert filtered.status_code == 200
    assert any(row["id"] == eid for row in filtered.json())
    # a filter that matches nothing
    empty = client.get(f"{BASE}?audit_type=surveillance", headers=h)
    assert empty.status_code == 200
    assert all(row["id"] != eid for row in empty.json())

    # get single
    got = client.get(f"{BASE}/{eid}", headers=h)
    assert got.status_code == 200, got.text
    assert got.json()["id"] == eid

    # transition planning -> fieldwork
    trans = client.post(f"{BASE}/{eid}/transition", headers=h, json={"new_status": "fieldwork"})
    assert trans.status_code == 200, trans.text
    assert trans.json()["status"] == "fieldwork"

    # dashboard reflects the engagement
    dash = client.get(f"{BASE}/dashboard", headers=h)
    assert dash.status_code == 200, dash.text
    assert dash.json()["total_engagements"] >= 1


def test_create_requires_audit_write(client, db_session):
    # auditor role lacks audit:write -> 403 (permission enforcement).
    org = bootstrap_org_user(client, email_prefix="ae-perm")
    auditor = add_org_member(db_session, client, org["organization_id"], "ae-auditor@example.com", role_name="auditor")
    r = client.post(BASE, headers=auditor, json=_create_body())
    assert r.status_code == 403, r.text


def test_transition_rejects_invalid_status_jump(client, db_session):
    # planning -> closed is not an allowed transition -> 422 (edge case).
    org = bootstrap_org_user(client, email_prefix="ae-edge")
    h = org["org_headers"]
    eid = _create(client, h)["id"]
    r = client.post(f"{BASE}/{eid}/transition", headers=h, json={"new_status": "closed"})
    assert r.status_code == 422, r.text


def test_get_missing_engagement_returns_404(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ae-404")
    r = client.get(f"{BASE}/{uuid.uuid4()}", headers=org["org_headers"])
    assert r.status_code == 404, r.text


def test_engagements_org_scoped(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="ae-a")
    eid = _create(client, org_a["org_headers"])["id"]

    org_b = bootstrap_org_user(client, email_prefix="ae-b")
    # org B cannot list org A's engagement
    listed_b = client.get(BASE, headers=org_b["org_headers"])
    assert listed_b.status_code == 200
    assert all(row["id"] != eid for row in listed_b.json())
    # org B cannot fetch it directly -> 404
    got_b = client.get(f"{BASE}/{eid}", headers=org_b["org_headers"])
    assert got_b.status_code == 404, got_b.text
