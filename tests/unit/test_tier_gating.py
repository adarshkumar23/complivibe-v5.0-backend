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


# ---- Stage 1c-4b: previously-unmapped packages ----

def _not_gate_broken(resp) -> bool:
    """True if the request was NOT intercepted by a feature gate or a
    gate-induced missing-org-header 400 (i.e. the public/machine path still
    reaches its own handler/auth)."""
    if _is_feature_blocked(resp):
        return False
    if resp.status_code == 400:
        try:
            if "X-Organization-ID" in str(resp.json().get("detail", "")):
                return False
        except Exception:
            pass
    return True


def test_dpdp_free_reads_open_writes_gated(client, tier_orgs):
    free = tier_orgs["free"]["org_headers"]
    # Free can READ the DPDP suite (conversion hook)...
    for path in ["/api/v1/privacy/ropa/activities", "/api/v1/privacy/notices",
                 "/api/v1/privacy/lawful-basis", "/api/v1/privacy/dpas",
                 "/api/v1/privacy/nominations", "/api/v1/privacy/dpias"]:
        r = client.get(path, headers=free)
        assert not _is_feature_blocked(r), f"DPDP read blocked for free: {path} -> {r.status_code} {r.text}"
    # ...but WRITES are gated by privacy_management (Free = False).
    w = client.post("/api/v1/privacy/ropa/activities", headers=free, json={})
    assert _is_feature_blocked(w), f"DPDP write not gated: {w.status_code} {w.text}"
    assert w.json()["detail"]["feature"] == "privacy_management"
    # Paid tiers (starter incl.) can write.
    for tier in ["trial", "starter", "growth", "enterprise"]:
        w2 = client.post("/api/v1/privacy/ropa/activities", headers=tier_orgs[tier]["org_headers"], json={})
        assert not _is_feature_blocked(w2), f"DPDP write blocked for {tier}: {w2.status_code}"


def test_new_c_modules_free_blocked_matrix(client, tier_orgs):
    # (feature, method, path, {tier: allowed})
    cases = [
        ("data_governance", "GET", "/api/v1/data-observability/assets",
         {"free": 0, "trial": 1, "starter": 0, "growth": 1, "enterprise": 1}),
        ("tprm_intelligence", "GET", "/api/v1/vendors/00000000-0000-0000-0000-000000000000/sanctions-screen",
         {"free": 0, "trial": 1, "starter": 0, "growth": 1, "enterprise": 1}),
        ("privacy_advanced", "POST", "/api/v1/privacy/sdf-designation/suggest",
         {"free": 0, "trial": 1, "starter": 1, "growth": 1, "enterprise": 1}),
        ("advanced_reporting", "GET", "/api/v1/compliance/policies/00000000-0000-0000-0000-000000000000/export",
         {"free": 0, "trial": 1, "starter": 0, "growth": 1, "enterprise": 1}),
        ("integrations_module", "GET", "/api/v1/cloud-connectors",
         {"free": 0, "trial": 1, "starter": 0, "growth": 1, "enterprise": 1}),
        ("integrations_module", "GET", "/api/v1/privacy/import/fides/status",
         {"free": 0, "trial": 1, "starter": 0, "growth": 1, "enterprise": 1}),
    ]
    for feature, method, path, expect in cases:
        for tier, allowed in expect.items():
            resp = client.request(method, path, headers=tier_orgs[tier]["org_headers"], json={} if method == "POST" else None)
            if allowed:
                assert not _is_feature_blocked(resp), f"{feature}/{tier} blocked: {path} {resp.status_code} {resp.text}"
            else:
                assert _is_feature_blocked(resp), f"{feature}/{tier} NOT blocked: {path} {resp.status_code} {resp.text}"
                assert resp.json()["detail"]["feature"] == feature


def test_ungated_packages_reachable_by_free(client, tier_orgs):
    free = tier_orgs["free"]["org_headers"]
    for method, path in [("GET", "/api/v1/preferences/digest"),
                         ("GET", "/api/v1/preferences/notifications"),
                         ("POST", "/api/v1/privacy/ccpa/opt-out")]:
        r = client.request(method, path, headers=free, json={} if method == "POST" else None)
        assert not _is_feature_blocked(r), f"ungated pkg blocked for free: {path} -> {r.status_code}"


def test_public_and_machine_paths_not_broken_by_gating(client, tier_orgs):
    # CRITICAL: gating must not break the public DSAR intake, machine key sinks,
    # public cookie banner, or agent-push ingests -- regardless of plan.
    free = tier_orgs["free"]["org_headers"]
    checks = [
        ("POST", "/api/v1/privacy/dsr/submit", free),                       # public DSAR intake
        ("POST", "/api/v1/privacy/consent/events", free),                   # machine (X-CompliVibe-Key)
        ("POST", "/api/v1/privacy/cookie-registry/scan-report", free),      # machine
        ("GET",  "/api/v1/privacy/consent-banner/some-org-slug", None),     # public, no auth
        ("POST", "/api/v1/cloud-connectors/ingest/aws/faketoken", None),    # machine HMAC
        ("POST", "/api/v1/security/ingest/trivy", None),                    # machine scanner
        ("POST", "/api/v1/data-observability/lineage/events", free),        # excluded from data_governance
        ("POST", "/api/v1/data-observability/access/events", free),         # excluded from data_governance
    ]
    for method, path, hdrs in checks:
        r = client.request(method, path, headers=hdrs, json={} if method == "POST" else None)
        assert _not_gate_broken(r), f"gating broke public/machine path {path}: {r.status_code} {r.text}"
    # And a paid org's machine ingest is equally unbroken (plan-independent).
    ent = tier_orgs["enterprise"]["org_headers"]
    r2 = client.post("/api/v1/privacy/consent/events", headers=ent, json={})
    assert _not_gate_broken(r2), f"enterprise machine ingest broken: {r2.status_code} {r2.text}"
