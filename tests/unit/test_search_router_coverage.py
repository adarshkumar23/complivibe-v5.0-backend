"""Coverage for the global search router (app/api/v1/search.py).

The endpoint (GET /api/v1/search) had no test exercising the HTTP surface -- the
only pre-existing search test (test_p1_11_search_index_bootstrap_on_startup.py)
asserts the lifespan wires up Meilisearch indexes and never calls the route.

Meilisearch is an external best-effort cache and is not running in the unit-test
environment, so the two "backend was reached" paths are driven by monkeypatching
`SearchIndexingService.search` (the service itself has its own tests). The
permission gate, the input-validation edges and the degraded fallback are all
real end-to-end through the FastAPI stack.

Every seeded RBAC role (owner/admin/compliance_manager/reviewer/auditor/readonly)
holds `search:read`, so the 403 path is exercised with a bespoke zero-permission
custom role -- the same technique used by test_legal_matters_coverage.py.
"""

from __future__ import annotations

import uuid

from app.services import search_indexing_service as sis_module
from app.services.search_indexing_service import SearchUnavailableError
from tests.helpers.auth_org import add_org_member, bootstrap_org_user

BASE = "/api/v1/search"


def _zero_permission_headers(db_session, client, organization_id: str, email: str) -> dict[str, str]:
    """A member on a custom role that holds NO permissions (so it lacks search:read)."""
    from app.models.role import Role

    role = Role(
        organization_id=uuid.UUID(organization_id),
        name=f"zero-perms-{uuid.uuid4().hex[:8]}",
        description="no permissions",
        is_system=False,
        is_system_role=False,
        is_active=True,
    )
    db_session.add(role)
    db_session.commit()
    return add_org_member(db_session, client, organization_id, email, role_name=role.name)


# --------------------------------------------------------------------------
# Permission enforcement
# --------------------------------------------------------------------------
def test_search_requires_search_read_permission(client, db_session):
    org = bootstrap_org_user(client, email_prefix="search-perm")
    no_perms = _zero_permission_headers(db_session, client, org["organization_id"], "search-noperm@example.com")
    resp = client.get(f"{BASE}?q=anything", headers=no_perms)
    assert resp.status_code == 403, resp.text


def test_search_allowed_for_readonly_role(client, db_session, monkeypatch):
    """The SAME query denied to a zero-perm role is allowed for a seeded role that
    holds search:read, proving the 403 above is the permission gate and not a
    blanket auth failure."""
    monkeypatch.setattr(
        sis_module.SearchIndexingService,
        "search",
        lambda self, **kwargs: {"query": kwargs["query"], "hits": [], "took_ms": 1},
    )
    org = bootstrap_org_user(client, email_prefix="search-ro")
    ro = add_org_member(db_session, client, org["organization_id"], "search-ro@example.com", role_name="readonly")
    resp = client.get(f"{BASE}?q=anything", headers=ro)
    assert resp.status_code == 200, resp.text


# --------------------------------------------------------------------------
# Happy path (backend reachable -- monkeypatched service)
# --------------------------------------------------------------------------
def test_search_happy_path_maps_hits(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="search-hit")
    org_id = org["organization_id"]

    def fake_search(self, *, query, organization_id, entity_types=None, limit=20):
        assert str(organization_id) == org_id  # endpoint passes the caller's org through
        return {
            "query": query,
            "took_ms": 7,
            "hits": [
                {
                    "entity_type": "risk",
                    "id": "risk-1",
                    "organization_id": org_id,
                    "_rankingScore": 0.95,
                    "title": "Data breach risk",
                },
                {
                    "entity_type": "vendor",
                    "id": "vendor-9",
                    "organization_id": org_id,
                    "_rankingScore": 0.42,
                },
            ],
        }

    monkeypatch.setattr(sis_module.SearchIndexingService, "search", fake_search)

    resp = client.get(f"{BASE}?q=breach&limit=5", headers=org["org_headers"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["query"] == "breach"
    assert body["took_ms"] == 7
    assert body["degraded"] is False
    assert len(body["hits"]) == 2
    first = body["hits"][0]
    assert first["entity_type"] == "risk"
    assert first["id"] == "risk-1"
    # score is serialized under its alias (_rankingScore) -- FastAPI response
    # models default to by_alias=True.
    assert first["_rankingScore"] == 0.95
    # extra="allow" passes entity-specific fields through untouched
    assert first["title"] == "Data breach risk"


def test_search_forwards_entity_type_filter(client, db_session, monkeypatch):
    """A valid entity_types filter is forwarded to the service unchanged."""
    captured = {}

    def fake_search(self, *, query, organization_id, entity_types=None, limit=20):
        captured["entity_types"] = entity_types
        captured["limit"] = limit
        return {"query": query, "hits": [], "took_ms": 0}

    monkeypatch.setattr(sis_module.SearchIndexingService, "search", fake_search)
    org = bootstrap_org_user(client, email_prefix="search-filter")
    resp = client.get(f"{BASE}?q=x&entity_types=risk&entity_types=vendor&limit=3", headers=org["org_headers"])
    assert resp.status_code == 200, resp.text
    assert captured["entity_types"] == ["risk", "vendor"]
    assert captured["limit"] == 3


# --------------------------------------------------------------------------
# Edge cases
# --------------------------------------------------------------------------
def test_search_invalid_entity_type_returns_400(client, db_session):
    """Unsupported entity_types are rejected BEFORE the service is called (400)."""
    org = bootstrap_org_user(client, email_prefix="search-badtype")
    resp = client.get(f"{BASE}?q=x&entity_types=not_a_real_type", headers=org["org_headers"])
    assert resp.status_code == 400, resp.text
    assert "Unsupported entity_types" in resp.json()["detail"]


def test_search_missing_query_returns_422(client, db_session):
    """`q` is required (min_length=1); omitting it is a validation error."""
    org = bootstrap_org_user(client, email_prefix="search-noq")
    resp = client.get(BASE, headers=org["org_headers"])
    assert resp.status_code == 422, resp.text


def test_search_degraded_when_backend_unavailable(client, db_session, monkeypatch):
    """When Meilisearch is unreachable the read path degrades to an empty 200
    with degraded=True rather than surfacing a hard 5xx."""

    def boom(self, **kwargs):
        raise SearchUnavailableError("connection refused")

    monkeypatch.setattr(sis_module.SearchIndexingService, "search", boom)
    org = bootstrap_org_user(client, email_prefix="search-degraded")
    resp = client.get(f"{BASE}?q=anything", headers=org["org_headers"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["degraded"] is True
    assert body["degraded_reason"] == "search_backend_unavailable"
    assert body["hits"] == []
    assert body["query"] == "anything"
