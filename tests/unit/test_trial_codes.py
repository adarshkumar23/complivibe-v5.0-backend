from __future__ import annotations

import hashlib
from uuid import UUID

from app.models.organization import Organization
from app.models.trial_code import TrialCode
from tests.helpers.auth_org import bootstrap_org_user


def _hash(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode("utf-8")).hexdigest()


def _insert_code(db_session, code: str, *, batch: str = "test") -> None:
    db_session.add(TrialCode(code_hash=_hash(code), code_prefix=code[:7], batch_label=batch))
    db_session.commit()


def _redeem(client, headers, code: str):
    return client.post("/api/v1/billing/redeem-trial-code", headers=headers, json={"code": code})


def _org(db_session, org_id: str) -> Organization:
    return db_session.get(Organization, UUID(org_id))


def test_free_org_can_reach_and_redeem_valid_code(client, db_session):
    # A newly-registered org is on Free (Stage 1c-1). The redeem endpoint lives
    # under /billing (Category D -- never feature-gated), so the Free org reaches
    # it (no 402/403) and a valid unused code moves it to Trial.
    org = bootstrap_org_user(client, email_prefix="tc-valid", plan="free")
    _insert_code(db_session, "CV-AAAA-1111-BBBB")

    resp = _redeem(client, org["org_headers"], "CV-AAAA-1111-BBBB")
    assert resp.status_code == 200, resp.text  # reachable by Free org, not gated
    body = resp.json()
    assert body["plan"] == "trial"
    assert body["subscription_status"] == "active"
    assert body["is_trial"] is True
    assert body["trial_days_remaining"] is not None and body["trial_days_remaining"] >= 13

    o = _org(db_session, org["organization_id"])
    assert o.subscription_plan == "trial" and o.subscription_status == "active"
    assert o.trial_ends_at is not None

    # Code is now marked redeemed to this org; DB stores only the hash.
    tc = db_session.query(TrialCode).filter_by(code_hash=_hash("CV-AAAA-1111-BBBB")).one()
    assert tc.redeemed_at is not None
    assert str(tc.redeemed_by_org_id) == org["organization_id"]
    assert tc.code_prefix == "CV-AAAA"


def test_reused_code_is_rejected(client, db_session):
    a = bootstrap_org_user(client, email_prefix="tc-reuse-a", plan="free")
    b = bootstrap_org_user(client, email_prefix="tc-reuse-b", plan="free")
    _insert_code(db_session, "CV-REUSE-CODE-01")

    first = _redeem(client, a["org_headers"], "CV-REUSE-CODE-01")
    assert first.status_code == 200
    second = _redeem(client, b["org_headers"], "CV-REUSE-CODE-01")
    assert second.status_code == 409
    assert second.json()["detail"]["error"] == "code_already_used"
    # B unaffected -- still Free.
    assert _org(db_session, b["organization_id"]).subscription_plan == "free"


def test_one_trial_per_org_lifetime(client, db_session):
    org = bootstrap_org_user(client, email_prefix="tc-lifetime", plan="free")
    _insert_code(db_session, "CV-LIFE-0001-AAAA")
    _insert_code(db_session, "CV-LIFE-0002-BBBB")

    assert _redeem(client, org["org_headers"], "CV-LIFE-0001-AAAA").status_code == 200
    # Even after the trial ends the org keeps trial_ends_at set, so a second
    # redemption is blocked for the org's lifetime. Simulate "trial over, back on
    # free" and confirm it is still blocked.
    o = _org(db_session, org["organization_id"])
    o.subscription_plan = "free"
    o.subscription_status = "active"
    db_session.commit()

    again = _redeem(client, org["org_headers"], "CV-LIFE-0002-BBBB")
    assert again.status_code == 409
    assert again.json()["detail"]["error"] == "already_trialed"
    # The second code was NOT consumed (eligibility checked before claim).
    tc2 = db_session.query(TrialCode).filter_by(code_hash=_hash("CV-LIFE-0002-BBBB")).one()
    assert tc2.redeemed_at is None


def test_invalid_code_rejected_cleanly(client, db_session):
    org = bootstrap_org_user(client, email_prefix="tc-invalid", plan="free")
    resp = _redeem(client, org["org_headers"], "CV-NOPE-NOPE-NOPE")
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "invalid_code"
    assert _org(db_session, org["organization_id"]).subscription_plan == "free"


def test_paid_org_not_eligible(client, db_session):
    org = bootstrap_org_user(client, email_prefix="tc-paid")
    o = _org(db_session, org["organization_id"])
    o.subscription_plan = "starter"  # already paid -> nothing to redeem
    o.subscription_status = "active"
    db_session.commit()
    _insert_code(db_session, "CV-PAID-0001-AAAA")

    resp = _redeem(client, org["org_headers"], "CV-PAID-0001-AAAA")
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "not_eligible"
    # code untouched
    tc = db_session.query(TrialCode).filter_by(code_hash=_hash("CV-PAID-0001-AAAA")).one()
    assert tc.redeemed_at is None
