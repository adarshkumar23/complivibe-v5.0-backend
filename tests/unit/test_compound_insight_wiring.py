from __future__ import annotations

"""Fast, PG-free guards for the compound-insight engine wiring.

Full behaviour (detection, dedup, notify, auto-resolve, tenant isolation, event
boundary) is covered on real Postgres in
tests/integration/test_compound_insight_engine.py. This pins the registry, the
permission scope, and the endpoint registration/auth gate.
"""

from app.compliance.services.compound_pattern_registry import PATTERN_REGISTRY, validate_registry
from app.services.seed_service import PERMISSIONS, ROLE_PERMISSION_MAP


def test_pattern_registry_validates_against_graph():
    validate_registry()  # raises on any node-type/edge-type drift
    assert [p.pattern_id for p in PATTERN_REGISTRY] == [
        "failed_control_stale_vendor_open_risk",
        "expired_evidence_control_open_risk",
        "active_incident_failed_control_stale_vendor",
    ]


def test_permission_scope_no_creep():
    assert "compound_insights:read" in PERMISSIONS
    granting = {r for r, codes in ROLE_PERMISSION_MAP.items() if "compound_insights:read" in codes}
    # owner/admin get everything by design; the 4 intended read roles get it explicitly.
    assert granting == {"owner", "admin", "compliance_manager", "reviewer", "auditor", "readonly"}


def test_endpoint_registered_and_requires_auth(client):
    # Missing X-Organization-ID -> 400 (route exists + resolves org first, like siblings).
    resp = client.get("/api/v1/compliance/compound-insights")
    assert resp.status_code in (400, 401)
    assert client.get("/api/v1/compliance/compound-insights/not-a-uuid-path-xyz/extra").status_code == 404
