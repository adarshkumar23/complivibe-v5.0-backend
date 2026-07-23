from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.models.organization import Organization
from tests.helpers.auth_org import bootstrap_org_user


def _policy_body(org):
    return {"title": f"p-{uuid4().hex[:6]}", "policy_type": "information_security", "owner_user_id": org["user_id"]}


def _control_body(org):
    return {"title": f"c-{uuid4().hex[:6]}", "control_type": "process", "criticality": "high"}


def _evidence_body(org):
    return {"title": f"e-{uuid4().hex[:6]}", "description": "e", "evidence_type": "document", "source": "manual"}


def _risk_body(org):
    return {"title": f"r-{uuid4().hex[:6]}", "category": "operational",
            "likelihood": 4, "impact": 4, "treatment_strategy": "mitigate"}


# (resource, path, body_builder)
RESOURCES = [
    ("policies", "/api/v1/compliance/policies", _policy_body),
    ("controls", "/api/v1/controls", _control_body),
    ("evidence", "/api/v1/evidence", _evidence_body),
    ("risks", "/api/v1/risks", _risk_body),
]


def _create(client, org, path, body):
    return client.post(path, headers=org["org_headers"], json=body)


def _set_plan(db_session, org_id: str, plan: str) -> None:
    o = db_session.get(Organization, UUID(org_id))
    o.subscription_plan = plan
    o.subscription_status = "active"
    o.trial_ends_at = (datetime.now(UTC) + timedelta(days=14)) if plan == "trial" else None
    db_session.commit()


@pytest.mark.parametrize("resource,path,body", RESOURCES, ids=[r[0] for r in RESOURCES])
def test_free_org_capped_at_five(client, db_session, resource, path, body):
    org = bootstrap_org_user(client, email_prefix=f"cap-{resource}", plan="free")
    for i in range(5):
        r = _create(client, org, path, body(org))
        assert r.status_code == 201, f"{resource} #{i + 1} failed: {r.status_code} {r.text}"
    # 6th is blocked with a clear, actionable 402.
    sixth = _create(client, org, path, body(org))
    assert sixth.status_code == 402, sixth.text
    detail = sixth.json()["detail"]
    assert detail["error"] == "record_cap_reached"
    assert detail["resource"] == resource
    assert detail["cap"] == 5
    assert detail["current_plan"] == "free"
    assert resource in detail["message"] and "upgrade" in detail["message"].lower()
    assert "/billing/upgrade" in detail["upgrade_url"]


@pytest.mark.parametrize("plan", ["trial", "enterprise"])
@pytest.mark.parametrize("resource,path,body", RESOURCES, ids=[r[0] for r in RESOURCES])
def test_paid_and_trial_uncapped(client, db_session, plan, resource, path, body):
    org = bootstrap_org_user(client, email_prefix=f"unc-{plan}-{resource}")
    _set_plan(db_session, org["organization_id"], plan)
    for i in range(6):  # well past the free cap of 5
        r = _create(client, org, path, body(org))
        assert r.status_code == 201, f"{plan}/{resource} #{i + 1} failed: {r.status_code} {r.text}"


def test_cap_is_org_scoped(client, db_session):
    a = bootstrap_org_user(client, email_prefix="cap-scope-a", plan="free")
    b = bootstrap_org_user(client, email_prefix="cap-scope-b", plan="free")
    for _ in range(5):
        assert _create(client, a, "/api/v1/risks", _risk_body(a)).status_code == 201
    # A is at its cap...
    assert _create(client, a, "/api/v1/risks", _risk_body(a)).status_code == 402
    # ...but B (its own count is 0) is unaffected.
    assert _create(client, b, "/api/v1/risks", _risk_body(b)).status_code == 201


def test_deleting_frees_a_slot(client, db_session):
    from app.models.control import Control

    org = bootstrap_org_user(client, email_prefix="cap-delete", plan="free")
    ids = []
    for _ in range(5):
        r = _create(client, org, "/api/v1/controls", _control_body(org))
        assert r.status_code == 201
        ids.append(r.json()["id"])
    assert _create(client, org, "/api/v1/controls", _control_body(org)).status_code == 402
    # Remove one row -> the cap is count-based (not a high-water mark), so a slot
    # frees and a new create succeeds.
    db_session.delete(db_session.get(Control, UUID(ids[0])))
    db_session.commit()
    assert _create(client, org, "/api/v1/controls", _control_body(org)).status_code == 201


def test_subcreates_on_capped_org_not_blocked(client, db_session):
    # A capped Free org can still operate on its existing <=5 records: a
    # sub-create (linking a control to a risk) is NOT one of the 4 gated create
    # paths and must keep working.
    org = bootstrap_org_user(client, email_prefix="cap-sub", plan="free")
    risk_id = _create(client, org, "/api/v1/risks", _risk_body(org)).json()["id"]
    control_id = _create(client, org, "/api/v1/controls", _control_body(org)).json()["id"]
    # fill risks to the cap so the org is definitely capped on risks
    for _ in range(4):
        assert _create(client, org, "/api/v1/risks", _risk_body(org)).status_code == 201
    assert _create(client, org, "/api/v1/risks", _risk_body(org)).status_code == 402  # risks capped

    # sub-create (link) on existing records still works
    link = client.post(f"/api/v1/risks/{risk_id}/controls", headers=org["org_headers"],
                       json={"control_id": control_id})
    assert link.status_code in (200, 201), link.text
