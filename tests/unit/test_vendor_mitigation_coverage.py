"""Coverage for the vendor mitigation endpoints
(/compliance/vendor-mitigation). Only incidental prior references.

Covers case create/get/list/transition + action add happy path, the summary
aggregation, vendor:write vs vendor:read permission enforcement, the
"assessment_id or ai_assessment_id required" 422 validation edge, and
org-scoping.
"""

from __future__ import annotations

import uuid

from tests.helpers.auth_org import add_org_member, bootstrap_org_user

VENDORS = "/api/v1/compliance/vendors"
AIVA = "/api/v1/compliance/ai-vendor-assessments"
BASE = "/api/v1/compliance/vendor-mitigation"


def _create_vendor(client, headers, owner_user_id: str) -> str:
    r = client.post(
        VENDORS,
        headers=headers,
        json={
            "name": f"Vendor {uuid.uuid4().hex[:8]}",
            "vendor_type": "software",
            "owner_user_id": owner_user_id,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_ai_assessment(client, headers, vendor_id: str) -> str:
    r = client.post(f"{AIVA}?vendor_id={vendor_id}", headers=headers, json={"model_type": "llm"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _case_body(vendor_id: str, ai_assessment_id: str, owner_id: str, **over) -> dict:
    body = {
        "vendor_id": vendor_id,
        "ai_assessment_id": ai_assessment_id,
        "title": "Remediate bias gap",
        "description": "Vendor must add bias testing and human oversight.",
        "severity": "high",
        "assigned_owner_id": owner_id,
        "due_date": "2027-01-01",
    }
    body.update(over)
    return body


def _bootstrap_case(client, headers, uid):
    vendor_id = _create_vendor(client, headers, uid)
    ai_id = _create_ai_assessment(client, headers, vendor_id)
    created = client.post(f"{BASE}/cases", headers=headers, json=_case_body(vendor_id, ai_id, uid))
    assert created.status_code == 201, created.text
    return vendor_id, ai_id, created.json()


def test_vendor_mitigation_happy_path(client, db_session):
    org = bootstrap_org_user(client, email_prefix="vm-happy")
    h, uid = org["org_headers"], org["user_id"]
    vendor_id, ai_id, case = _bootstrap_case(client, h, uid)

    assert case["status"] == "open"
    assert case["severity"] == "high"
    assert case["vendor_id"] == vendor_id
    assert case["ai_assessment_id"] == ai_id
    assert case["assigned_owner_id"] == uid
    assert case["created_by"] == uid
    case_id = case["id"]

    # get
    got = client.get(f"{BASE}/cases/{case_id}", headers=h)
    assert got.status_code == 200, got.text
    assert got.json()["id"] == case_id

    # list (org-scoped, contains it)
    listed = client.get(f"{BASE}/cases", headers=h)
    assert listed.status_code == 200
    assert any(r["id"] == case_id for r in listed.json())

    # add an action to the open case
    action = client.post(
        f"{BASE}/cases/{case_id}/actions",
        headers=h,
        json={
            "title": "Enable bias testing",
            "description": "Run quarterly bias tests.",
            "action_type": "technical_control",
            "assigned_to_vendor": True,
            "due_date": "2027-01-01",
        },
    )
    assert action.status_code == 201, action.text
    assert action.json()["status"] == "open"
    assert action.json()["case_id"] == case_id

    # actions list contains it
    actions = client.get(f"{BASE}/cases/{case_id}/actions", headers=h)
    assert actions.status_code == 200
    assert len(actions.json()) == 1

    # transition open -> in_progress (a valid transition)
    trans = client.post(f"{BASE}/cases/{case_id}/transition", headers=h, json={"new_status": "in_progress"})
    assert trans.status_code == 200, trans.text
    assert trans.json()["status"] == "in_progress"

    # summary reflects the case + action
    summary = client.get(f"{BASE}/cases/summary", headers=h)
    assert summary.status_code == 200, summary.text
    s = summary.json()
    assert s["total_cases"] == 1
    assert s["by_status"] == {"in_progress": 1}
    assert s["by_severity"] == {"high": 1}
    assert s["total_actions"] == 1


def test_vendor_mitigation_invalid_transition_422(client, db_session):
    org = bootstrap_org_user(client, email_prefix="vm-trans")
    h, uid = org["org_headers"], org["user_id"]
    _v, _a, case = _bootstrap_case(client, h, uid)
    # open -> closed is not an allowed transition
    r = client.post(f"{BASE}/cases/{case['id']}/transition", headers=h, json={"new_status": "closed"})
    assert r.status_code == 422, r.text


def test_vendor_mitigation_requires_assessment_ref_422(client, db_session):
    org = bootstrap_org_user(client, email_prefix="vm-ref")
    h, uid = org["org_headers"], org["user_id"]
    vendor_id = _create_vendor(client, h, uid)
    # neither assessment_id nor ai_assessment_id -> 422
    body = {
        "vendor_id": vendor_id,
        "title": "No ref",
        "description": "Missing assessment reference.",
        "severity": "low",
        "assigned_owner_id": uid,
        "due_date": "2027-01-01",
    }
    r = client.post(f"{BASE}/cases", headers=h, json=body)
    assert r.status_code == 422, r.text


def test_vendor_mitigation_create_requires_vendor_write(client, db_session):
    org = bootstrap_org_user(client, email_prefix="vm-perm")
    h, uid = org["org_headers"], org["user_id"]
    vendor_id = _create_vendor(client, h, uid)
    ai_id = _create_ai_assessment(client, h, vendor_id)

    # readonly has vendor:read but lacks vendor:write
    ro = add_org_member(db_session, client, org["organization_id"], "vm-readonly@example.com", role_name="readonly")

    forbidden = client.post(f"{BASE}/cases", headers=ro, json=_case_body(vendor_id, ai_id, uid))
    assert forbidden.status_code == 403, forbidden.text

    # but a read endpoint (vendor:read) is allowed for readonly
    allowed = client.get(f"{BASE}/cases", headers=ro)
    assert allowed.status_code == 200, allowed.text


def test_vendor_mitigation_org_scoped(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="vm-a")
    ha, uida = org_a["org_headers"], org_a["user_id"]
    _v, _a, case = _bootstrap_case(client, ha, uida)
    case_id = case["id"]

    org_b = bootstrap_org_user(client, email_prefix="vm-b")
    hb = org_b["org_headers"]

    # org B cannot see org A's case in its list...
    listed_b = client.get(f"{BASE}/cases", headers=hb)
    assert listed_b.status_code == 200
    assert all(r["id"] != case_id for r in listed_b.json())

    # ...nor fetch it directly (org-scoped 404)
    got_b = client.get(f"{BASE}/cases/{case_id}", headers=hb)
    assert got_b.status_code == 404, got_b.text
