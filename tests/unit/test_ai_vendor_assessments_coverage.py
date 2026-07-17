"""Coverage for the AI vendor assessment endpoints
(/compliance/ai-vendor-assessments). Only incidental prior references.

Covers create/get/list/summary/complete happy path (asserting the real
computed risk score/level), vendor:write vs vendor:read permission
enforcement, a not-found 404 edge case, and org-scoping.
"""

from __future__ import annotations

import uuid

from tests.helpers.auth_org import add_org_member, bootstrap_org_user

VENDORS = "/api/v1/compliance/vendors"
BASE = "/api/v1/compliance/ai-vendor-assessments"


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


def _assessment_body(**over) -> dict:
    body = {
        "ai_model_name": "acme-gpt",
        "ai_model_provider": "Acme",
        "model_type": "llm",
        "data_exits_environment": True,
        "bias_testing_performed": False,
        "human_oversight_required": False,
        "output_used_for_decisions": True,
        "regulatory_obligations": ["EU_AI_ACT", "GDPR"],
    }
    body.update(over)
    return body


def test_ai_vendor_assessment_happy_path(client, db_session):
    org = bootstrap_org_user(client, email_prefix="aiva-happy")
    h, uid = org["org_headers"], org["user_id"]
    vendor_id = _create_vendor(client, h, uid)

    # create (vendor_id is a query param)
    created = client.post(f"{BASE}?vendor_id={vendor_id}", headers=h, json=_assessment_body())
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["vendor_id"] == vendor_id
    assert row["assessor_id"] == uid
    assert row["status"] == "draft"
    assert row["ai_model_name"] == "acme-gpt"
    assert row["risk_score"] is None
    aid = row["id"]

    # get
    got = client.get(f"{BASE}/{aid}", headers=h)
    assert got.status_code == 200, got.text
    assert got.json()["id"] == aid

    # list (org-scoped, contains it)
    listed = client.get(BASE, headers=h)
    assert listed.status_code == 200
    assert any(r["id"] == aid for r in listed.json())

    # complete -> computes real risk score/level and freezes status
    done = client.post(f"{BASE}/{aid}/complete", headers=h)
    assert done.status_code == 200, done.text
    finished = done.json()
    assert finished["status"] == "completed"
    # data_exits(+30) + no_bias(+20) + no_oversight&decisions(+25) + no_gov(+15)
    # + no_explainability(+10) + 2 obligations(+10) = 110 -> clamped 100 -> critical
    assert finished["risk_score"] == 100
    assert finished["overall_risk_level"] == "critical"
    assert finished["completed_at"] is not None

    # summary reflects the completed assessment
    summary = client.get(f"{BASE}/summary", headers=h)
    assert summary.status_code == 200, summary.text
    s = summary.json()
    assert s["total_assessments"] == 1
    assert s["by_status"] == {"completed": 1}
    assert s["critical_count"] == 1
    assert s["data_exits_count"] == 1
    assert s["no_bias_testing_count"] == 1
    assert s["no_human_oversight_decisions_count"] == 1


def test_ai_vendor_assessment_create_requires_vendor_write(client, db_session):
    org = bootstrap_org_user(client, email_prefix="aiva-perm")
    h, uid = org["org_headers"], org["user_id"]
    vendor_id = _create_vendor(client, h, uid)

    # readonly has vendor:read but lacks vendor:write
    ro = add_org_member(db_session, client, org["organization_id"], "aiva-readonly@example.com", role_name="readonly")

    forbidden = client.post(f"{BASE}?vendor_id={vendor_id}", headers=ro, json=_assessment_body())
    assert forbidden.status_code == 403, forbidden.text

    # but a read endpoint (vendor:read) is allowed for readonly
    allowed = client.get(BASE, headers=ro)
    assert allowed.status_code == 200, allowed.text


def test_ai_vendor_assessment_get_not_found(client, db_session):
    org = bootstrap_org_user(client, email_prefix="aiva-404")
    r = client.get(f"{BASE}/{uuid.uuid4()}", headers=org["org_headers"])
    assert r.status_code == 404, r.text


def test_ai_vendor_assessment_org_scoped(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="aiva-a")
    ha, uida = org_a["org_headers"], org_a["user_id"]
    vendor_a = _create_vendor(client, ha, uida)
    created = client.post(f"{BASE}?vendor_id={vendor_a}", headers=ha, json=_assessment_body())
    assert created.status_code == 201
    aid = created.json()["id"]

    org_b = bootstrap_org_user(client, email_prefix="aiva-b")
    hb = org_b["org_headers"]

    # org B cannot see org A's assessment in its list...
    listed_b = client.get(BASE, headers=hb)
    assert listed_b.status_code == 200
    assert all(r["id"] != aid for r in listed_b.json())

    # ...nor fetch it directly (org-scoped 404)
    got_b = client.get(f"{BASE}/{aid}", headers=hb)
    assert got_b.status_code == 404, got_b.text
