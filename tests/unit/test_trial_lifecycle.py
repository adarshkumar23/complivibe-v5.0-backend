from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select

from app.models.audit_log import AuditLog
from app.models.compliance_policy import CompliancePolicy
from app.models.email_outbox import EmailOutbox
from app.models.organization import Organization
from app.models.trial_code import TrialCode
from app.platform.services.trial_lifecycle_service import run_daily_trial_lifecycle_sweep
from tests.helpers.auth_org import bootstrap_org_user

GATED_C = "/api/v1/synthetic-datasets"  # ai_governance_module (Free = blocked)


def _policy_body(org):
    return {"title": f"p-{uuid4().hex[:6]}", "policy_type": "information_security", "owner_user_id": org["user_id"]}


def _expire_trial(db_session, org_id: str, *, days_ago: int = 1) -> None:
    o = db_session.get(Organization, UUID(org_id))
    o.subscription_plan = "trial"
    o.subscription_status = "active"
    o.trial_ends_at = datetime.now(UTC) - timedelta(days=days_ago)
    db_session.commit()


def _org(db_session, org_id: str) -> Organization:
    o = db_session.get(Organization, UUID(org_id))
    db_session.refresh(o)
    return o


def test_lazy_downgrade_not_a_402_deadend(client, db_session):
    org = bootstrap_org_user(client, email_prefix="tl-lazy", plan="trial")
    _expire_trial(db_session, org["organization_id"])
    # A gated request from an expired trial is NOT a 402 dead-end: the org is
    # lazily downgraded to Free and then evaluated as Free (403 on a premium C
    # module -- because Free lacks it -- not 402 trial_expired).
    r = client.get(GATED_C, headers=org["org_headers"])
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["error"] == "feature_not_in_plan"
    # Transition persisted (committed by the gate).
    o = _org(db_session, org["organization_id"])
    assert o.subscription_plan == "free" and o.subscription_status == "active"
    assert o.trial_ends_at is not None  # kept -> re-redeem stays blocked
    # Audited exactly once.
    audits = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == UUID(org["organization_id"]),
            AuditLog.action == "subscription.trial_expired_downgraded",
        )
    ).scalars().all()
    assert len(audits) == 1


def test_free_tier_behavior_after_downgrade(client, db_session):
    org = bootstrap_org_user(client, email_prefix="tl-freebehav", plan="trial")
    _expire_trial(db_session, org["organization_id"])
    # trigger downgrade
    client.get(GATED_C, headers=org["org_headers"])
    # Now behaves as Free: can reach Category D + read Category B, blocked on C writes/reads.
    assert client.get("/api/v1/billing/status", headers=org["org_headers"]).status_code == 200
    assert client.get("/api/v1/compliance/vendors/summary", headers=org["org_headers"]).status_code != 403  # B read open
    w = client.post("/api/v1/compliance/vendors", headers=org["org_headers"], json={})  # B write gated for free
    assert w.status_code == 403 and w.json()["detail"]["error"] == "feature_not_in_plan"


def test_data_kept_and_over_cap_after_downgrade(client, db_session):
    org = bootstrap_org_user(client, email_prefix="tl-data", plan="trial")
    org_id = UUID(org["organization_id"])
    # Create 20 policies on trial (uncapped).
    for _ in range(20):
        r = client.post("/api/v1/compliance/policies", headers=org["org_headers"], json=_policy_body(org))
        assert r.status_code == 201, r.text
    _expire_trial(db_session, org["organization_id"])

    # First post-expiry create -> lazily downgraded to Free, and the 21st is
    # cleanly capped (not a weird error).
    twenty_first = client.post("/api/v1/compliance/policies", headers=org["org_headers"], json=_policy_body(org))
    assert twenty_first.status_code == 402, twenty_first.text
    detail = twenty_first.json()["detail"]
    assert detail["error"] == "record_cap_reached"
    assert detail["resource"] == "policies" and detail["cap"] == 5
    assert _org(db_session, org["organization_id"]).subscription_plan == "free"

    # DATA KEPT: all 20 still exist in the DB and are READABLE via the API.
    kept = db_session.execute(
        select(func.count()).select_from(CompliancePolicy).where(CompliancePolicy.organization_id == org_id)
    ).scalar_one()
    assert kept == 20, f"expected 20 policies kept, found {kept}"
    listing = client.get("/api/v1/compliance/policies", headers=org["org_headers"])
    assert listing.status_code == 200  # readable, not blocked


def test_reredeem_blocked_after_expiry(client, db_session):
    org = bootstrap_org_user(client, email_prefix="tl-rr", plan="trial")
    _expire_trial(db_session, org["organization_id"])
    client.get(GATED_C, headers=org["org_headers"])  # downgrade
    assert _org(db_session, org["organization_id"]).subscription_plan == "free"

    code = "CV-RR01-RR02-RR03"
    db_session.add(TrialCode(code_hash=hashlib.sha256(code.upper().encode()).hexdigest(), code_prefix=code[:7]))
    db_session.commit()
    resp = client.post("/api/v1/billing/redeem-trial-code", headers=org["org_headers"], json={"code": code})
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "already_trialed"  # one trial per lifetime holds


def test_sweep_downgrades_dormant_expired_trial(client, db_session):
    org = bootstrap_org_user(client, email_prefix="tl-sweep", plan="trial")
    _expire_trial(db_session, org["organization_id"])  # NO request made (dormant)

    result = run_daily_trial_lifecycle_sweep(db_session)
    db_session.commit()
    assert result["downgraded"] >= 1
    assert _org(db_session, org["organization_id"]).subscription_plan == "free"
    # Idempotent: a second run downgrades nothing.
    result2 = run_daily_trial_lifecycle_sweep(db_session)
    db_session.commit()
    assert result2["downgraded"] == 0


def test_other_tiers_never_touched(client, db_session):
    orgs = {t: bootstrap_org_user(client, email_prefix=f"tl-keep-{t}", plan=t)
            for t in ["free", "starter", "growth", "enterprise"]}
    # Even with a stale past trial_ends_at, a non-trial plan is never downgraded.
    for o in orgs.values():
        oo = db_session.get(Organization, UUID(o["organization_id"]))
        oo.trial_ends_at = datetime.now(UTC) - timedelta(days=5)
        db_session.commit()
    run_daily_trial_lifecycle_sweep(db_session)  # sweep
    db_session.commit()
    for o in orgs.values():  # lazy path
        client.get(GATED_C, headers=o["org_headers"])
    for tier, o in orgs.items():
        assert _org(db_session, o["organization_id"]).subscription_plan == tier, f"{tier} was changed"


def test_expiry_warnings_t3_t1_and_dedup(client, db_session):
    org = bootstrap_org_user(client, email_prefix="tl-warn", plan="trial")
    org_id = UUID(org["organization_id"])

    def _outbox(event_type):
        return db_session.execute(
            select(EmailOutbox).where(EmailOutbox.organization_id == org_id, EmailOutbox.event_type == event_type)
        ).scalars().all()

    # 2 days left -> T-3 window matches, T-1 not yet.
    o = db_session.get(Organization, org_id)
    o.trial_ends_at = datetime.now(UTC) + timedelta(days=2)
    db_session.commit()
    run_daily_trial_lifecycle_sweep(db_session)
    db_session.commit()
    t3 = _outbox("trial.expiry.warning.t3")
    assert len(t3) >= 1 and len(_outbox("trial.expiry.warning.t1")) == 0
    assert "/billing/upgrade" in t3[0].body_text  # includes upgrade path

    # Re-run -> no duplicate T-3.
    run_daily_trial_lifecycle_sweep(db_session)
    db_session.commit()
    assert len(_outbox("trial.expiry.warning.t3")) == len(t3)

    # <1 day left -> T-1 fires.
    o = db_session.get(Organization, org_id)
    o.trial_ends_at = datetime.now(UTC) + timedelta(hours=12)
    db_session.commit()
    run_daily_trial_lifecycle_sweep(db_session)
    db_session.commit()
    assert len(_outbox("trial.expiry.warning.t1")) >= 1
