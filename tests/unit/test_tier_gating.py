from __future__ import annotations

import pytest

from tests.helpers.auth_org import bootstrap_org_user

TIERS = ["free", "trial", "starter", "growth", "enterprise"]

# Category C: whole-router feature gate. One representative GET per flag, plus
# the expected access per tier (1 = allowed, 0 = 403 feature_not_in_plan).
# Mirrors the locked plan->flag matrix.
C_MATRIX = {
    "ai_governance_module":     ("/api/v1/synthetic-datasets",                  {"free": 0, "trial": 1, "starter": 0, "growth": 1, "enterprise": 1}),
    "governance_autopilot":     ("/api/v1/governance/retention/policies",       {"free": 0, "trial": 1, "starter": 0, "growth": 0, "enterprise": 1}),
    "resilience_module":        ("/api/v1/compliance/dora/ict-register",        {"free": 0, "trial": 1, "starter": 0, "growth": 1, "enterprise": 1}),
    "privacy_advanced":         ("/api/v1/legal-matters",                       {"free": 0, "trial": 1, "starter": 1, "growth": 1, "enterprise": 1}),
    "audit_assurance":          ("/api/v1/compliance/audit-engagements",        {"free": 0, "trial": 1, "starter": 0, "growth": 1, "enterprise": 1}),
    "advanced_analytics":       ("/api/v1/compliance/risk-appetite",            {"free": 0, "trial": 1, "starter": 0, "growth": 1, "enterprise": 1}),
    "advanced_reporting":       ("/api/v1/compliance/custom-report-templates",  {"free": 0, "trial": 1, "starter": 0, "growth": 1, "enterprise": 1}),
    "integrations_module":      ("/api/v1/connectors/catalog",                  {"free": 0, "trial": 1, "starter": 0, "growth": 1, "enterprise": 1}),
    "questionnaire_management": ("/api/v1/compliance/questionnaire-templates",  {"free": 0, "trial": 1, "starter": 1, "growth": 1, "enterprise": 1}),
    "identity_governance":      ("/api/v1/access-certifications/campaigns",     {"free": 0, "trial": 1, "starter": 0, "growth": 0, "enterprise": 1}),
    "specialized_modules":      ("/api/v1/sod-conflicts/rules",                 {"free": 0, "trial": 1, "starter": 0, "growth": 0, "enterprise": 1}),
}


@pytest.fixture
def tier_orgs(client):
    return {t: bootstrap_org_user(client, email_prefix=f"gate-{t}", plan=t) for t in TIERS}


def _is_feature_blocked(resp) -> bool:
    if resp.status_code != 403:
        return False
    try:
        return resp.json().get("detail", {}).get("error") == "feature_not_in_plan"
    except Exception:
        return False


def test_category_c_router_gate_tier_matrix(client, tier_orgs):
    for flag, (path, expect) in C_MATRIX.items():
        for tier, allowed in expect.items():
            resp = client.get(path, headers=tier_orgs[tier]["org_headers"])
            if allowed:
                assert not _is_feature_blocked(resp), f"{flag}/{tier} unexpectedly BLOCKED: {resp.status_code} {resp.text}"
            else:
                assert _is_feature_blocked(resp), f"{flag}/{tier} not blocked: {resp.status_code} {resp.text}"
                detail = resp.json()["detail"]
                assert detail["feature"] == flag
                assert detail["current_plan"] == tier


def test_category_b_writes_gated_reads_open(client, tier_orgs):
    # vendor_management (Category B): READS open to every tier incl free...
    for tier in TIERS:
        r = client.get("/api/v1/compliance/vendors/summary", headers=tier_orgs[tier]["org_headers"])
        assert not _is_feature_blocked(r), f"vendor read blocked for {tier}: {r.status_code} {r.text}"

    # ...but WRITES are feature-gated: only Free (vendor_management False) is blocked.
    expect_write_blocked = {"free": True, "trial": False, "starter": False, "growth": False, "enterprise": False}
    for tier, blocked in expect_write_blocked.items():
        w = client.post("/api/v1/compliance/vendors", headers=tier_orgs[tier]["org_headers"], json={})
        if blocked:
            assert _is_feature_blocked(w), f"vendor write NOT blocked for {tier}: {w.status_code} {w.text}"
            assert w.json()["detail"]["feature"] == "vendor_management"
        else:
            assert not _is_feature_blocked(w), f"vendor write blocked for paid {tier}: {w.status_code} {w.text}"


def test_privacy_basic_lets_free_write_breach(client, tier_orgs):
    # privacy_basic is TRUE for every tier incl free -> the write gate never blocks.
    w = client.post("/api/v1/compliance/breach-notifications", headers=tier_orgs["free"]["org_headers"], json={})
    assert not _is_feature_blocked(w), f"free breach write blocked: {w.status_code} {w.text}"


def test_free_reaches_category_d(client):
    # A Free org can always reach the essentials it needs to function & upgrade.
    free = bootstrap_org_user(client, email_prefix="gate-d", plan="free")
    for path in [
        "/api/v1/billing/status",           # billing
        "/api/v1/billing/plans",            # pricing/plans (public)
        "/api/v1/organizations/me",         # own org
        "/api/v1/auth/me",                  # own profile
        "/api/v1/dashboard/summary",        # own-data dashboard
    ]:
        r = client.get(path, headers=free["org_headers"])
        assert r.status_code != 403, f"Free blocked on Category-D {path}: {r.status_code} {r.text}"


def test_excluded_scoped_key_router_not_feature_gated(client):
    # whistleblower is an EXCLUDED router (public reporter submit) -- it must NOT
    # be feature-gated, so a Free org (like any caller) is never feature-blocked
    # on it. This mirrors why patent/machine scoped-key routers are excluded:
    # require_feature can't run without a session org, and key issuance is the
    # real control there.
    free = bootstrap_org_user(client, email_prefix="gate-excl", plan="free")
    r = client.post("/api/v1/whistleblower/submit", headers=free["org_headers"], json={})
    assert not _is_feature_blocked(r), f"excluded router feature-gated: {r.status_code} {r.text}"
