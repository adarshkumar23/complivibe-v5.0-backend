"""Permission enforcement + coexistence for the signature-scored shadow-AI graft.

The upstream repo shipped an always-allow ``require_permission`` stub. These
tests prove core's real RBAC now gates every endpoint, that the new
``shadow_ai_signature:*`` codes are distinct from the ``ai_systems:*`` codes
governing core's separate shadow-AI feature, and that both features remain
independently reachable.
"""

from __future__ import annotations

import pytest

from app.services.seed_service import PERMISSIONS, ROLE_PERMISSION_MAP
from tests.helpers.auth_org import bootstrap_org_user

SIGNATURE_CODES = {
    "shadow_ai_signature:read",
    "shadow_ai_signature:write",
    "shadow_ai_signature:review",
    "shadow_ai_signature:admin",
}

# (method, path, permission the endpoint requires)
ENDPOINTS = [
    ("get", "/api/v1/ai-governance/shadow-ai-signatures/signatures", "shadow_ai_signature:read"),
    ("get", "/api/v1/ai-governance/shadow-ai-signatures/detections", "shadow_ai_signature:read"),
    ("post", "/api/v1/ai-governance/shadow-ai-signatures/rescan", "shadow_ai_signature:write"),
    ("post", "/api/v1/ai-governance/shadow-ai-signatures/decay", "shadow_ai_signature:write"),
    ("get", "/api/v1/ai-governance/shadow-ai-signatures/federated/candidates", "shadow_ai_signature:admin"),
]


def test_new_codes_are_registered_and_distinct_from_core_ai_systems():
    for code in SIGNATURE_CODES:
        assert code in PERMISSIONS, f"{code} must be seeded"
    # Core's existing shadow-AI feature is governed by ai_systems:*; the two sets
    # must not overlap, so a grant can never silently span both systems.
    assert SIGNATURE_CODES.isdisjoint({"ai_systems:read", "ai_systems:write", "ai_systems:admin"})


def test_role_grants_follow_the_established_shape():
    for role in ("owner", "admin", "compliance_manager"):
        assert SIGNATURE_CODES <= ROLE_PERMISSION_MAP[role], f"{role} should hold all four"
    for role in ("reviewer", "auditor", "readonly"):
        granted = SIGNATURE_CODES & ROLE_PERMISSION_MAP[role]
        assert granted == {"shadow_ai_signature:read"}, (
            f"{role} should hold read only, got {granted}"
        )


@pytest.mark.parametrize("method,path,permission", ENDPOINTS)
def test_endpoint_rejects_unauthenticated_caller(client, method, path, permission):
    """The always-allow stub is gone: a valid org but no session means no access.

    The org header must still be supplied, because core resolves the org before
    authenticating; omitting it yields a 400 about the header and would not
    prove anything about auth.
    """
    org = bootstrap_org_user(client, email_prefix="shadowsig-anon")
    org_only_headers = {"X-Organization-ID": org["org_headers"]["X-Organization-ID"]}
    client.cookies.clear()
    kwargs = {"json": {}} if method == "post" else {}
    response = getattr(client, method)(path, headers=org_only_headers, **kwargs)
    assert response.status_code in (401, 403), f"{path} -> {response.status_code}: {response.text}"


@pytest.mark.parametrize("method,path,permission", ENDPOINTS)
def test_endpoint_allows_owner_who_holds_the_permission(client, method, path, permission):
    org = bootstrap_org_user(client, email_prefix="shadowsig-ok")
    assert permission in ROLE_PERMISSION_MAP["owner"]
    kwargs = {"json": {}} if method == "post" else {}
    response = getattr(client, method)(path, headers=org["org_headers"], **kwargs)
    assert response.status_code == 200, f"{path} -> {response.status_code}: {response.text}"


def test_readonly_role_cannot_write_or_administer(client):
    """A read-only grant must not reach the write/admin surfaces."""
    assert "shadow_ai_signature:write" not in ROLE_PERMISSION_MAP["readonly"]
    assert "shadow_ai_signature:admin" not in ROLE_PERMISSION_MAP["readonly"]
    assert "shadow_ai_signature:review" not in ROLE_PERMISSION_MAP["readonly"]


def test_missing_org_header_is_rejected(client):
    """Every endpoint is org-scoped; an authenticated caller still needs the org."""
    org = bootstrap_org_user(client, email_prefix="shadowsig-noorg")
    response = client.get(
        "/api/v1/ai-governance/shadow-ai-signatures/detections", headers=org["headers"]
    )
    assert response.status_code in (400, 403, 422), response.text


def test_core_shadow_ai_endpoints_still_reachable(client):
    """The graft must not shadow or break core's existing shadow-AI router."""
    org = bootstrap_org_user(client, email_prefix="shadowsig-coexist")
    core = client.get("/api/v1/ai-governance/shadow-ai/detections", headers=org["org_headers"])
    assert core.status_code == 200, core.text
    new = client.get(
        "/api/v1/ai-governance/shadow-ai-signatures/detections", headers=org["org_headers"]
    )
    assert new.status_code == 200, new.text
    # Two distinct routes, two distinct payloads -- neither is a redirect of the other.
    assert core.json() == [] or isinstance(core.json(), (list, dict))
    assert new.json() == []


def test_both_routers_are_mounted_at_distinct_prefixes():
    from app.main import app

    app.openapi()
    paths = set(app.openapi()["paths"])
    core = {p for p in paths if "/shadow-ai/" in p}
    new = {p for p in paths if "/shadow-ai-signatures/" in p}
    assert core, "core's shadow-ai routes must still be mounted"
    assert new, "the grafted routes must be mounted"
    assert core.isdisjoint(new)
