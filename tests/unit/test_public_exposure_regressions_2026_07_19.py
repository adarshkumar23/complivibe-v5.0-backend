"""Regression tests for two issues found during the 2026-07-19 FEATURE_INVENTORY code walk.

1. GET /trust-center/{slug} is an intentionally public, unauthenticated tenant page, but it
   also rendered the platform-global competitor-pricing table. That table is CompliVibe's own
   competitive-research content: it is not tenant data, it is not gated by any of the config's
   show_* toggles, and a tenant cannot switch it off. It must not appear on a tenant's page.

2. GET /obligations/{id} declares X-Organization-ID as optional (Header(default=None)) and
   _build_obligation_read already accepts organization_id=None, but the endpoint dereferenced
   `organization.id` unconditionally on the return path -- so omitting the header raised
   UnboundLocalError and surfaced as a 500.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.obligation import Obligation
from app.services.seed_service import SeedService
from tests.helpers.auth_org import bootstrap_org_user


def _enable_trust_center(client, org, **overrides) -> str:
    """Turn on the public trust center for the bootstrapped org and return its slug."""
    orgs = client.get("/api/v1/organizations/me", headers=org["headers"])
    assert orgs.status_code == 200, orgs.text
    slug = orgs.json()[0]["slug"]

    body = {
        "is_enabled": True,
        "display_name": "Public Trust Center",
        "show_certifications": True,
        "show_framework_coverage": True,
        "show_published_policies": True,
        "show_uptime_status": True,
        "request_access_enabled": True,
    }
    body.update(overrides)

    response = client.post(
        "/api/v1/compliance/trust-center/configuration",
        headers=org["org_headers"],
        json=body,
    )
    assert response.status_code == 200, response.text
    return slug


def test_public_trust_center_does_not_expose_competitor_pricing(client):
    """An unauthenticated trust-center read must not leak the competitor-pricing table."""
    org = bootstrap_org_user(client, email_prefix="trust-pricing-leak")
    slug = _enable_trust_center(client, org)

    # Registration/login leaves an httpOnly cv_session cookie in the TestClient jar. Clear it,
    # otherwise this request is silently authenticated and the test proves nothing.
    client.cookies.clear()
    response = client.get(f"/api/v1/trust-center/{slug}")
    assert response.status_code == 200, response.text
    payload = response.json()

    assert "competitor_pricing" not in payload
    assert "competitor_pricing_last_updated" not in payload

    # Belt and braces: no competitor name should appear anywhere in the serialized body,
    # so a future refactor cannot smuggle the same content back under a different key.
    body_text = response.text.lower()
    for competitor in ("vanta", "drata", "sprinto", "scrut", "onetrust"):
        assert competitor not in body_text, f"{competitor!r} leaked into the public trust center payload"


def test_public_trust_center_still_serves_its_legitimate_content(client):
    """The public trust page itself must keep working -- this fix must not over-correct."""
    org = bootstrap_org_user(client, email_prefix="trust-still-public")
    slug = _enable_trust_center(client, org)

    client.cookies.clear()
    response = client.get(f"/api/v1/trust-center/{slug}")
    assert response.status_code == 200, response.text
    payload = response.json()

    # Still anonymous, still a working tenant-facing trust page.
    assert payload["organization_slug"] == slug
    assert payload["display_name"] == "Public Trust Center"
    for key in ("certifications", "framework_coverage", "policies"):
        assert key in payload, f"public trust center lost its {key} section"
    assert "data_generated_at" in payload


def test_competitor_pricing_endpoint_requires_authentication(client):
    """GET /pricing serves the same internal research table and must not be anonymous."""
    # Explicit even though this test never logs in: a future edit that bootstraps an org here
    # would otherwise make this pass via the session cookie without actually testing anything.
    client.cookies.clear()
    response = client.get("/api/v1/pricing")
    assert response.status_code in (401, 403), response.text


def test_competitor_pricing_endpoint_readable_by_authenticated_user(client):
    """Gating /pricing must not break the authenticated in-product read."""
    org = bootstrap_org_user(client, email_prefix="pricing-authed")

    response = client.get("/api/v1/pricing", headers=org["org_headers"])
    assert response.status_code == 200, response.text
    assert response.json()["entries"]


def test_obligation_detail_without_org_header_does_not_500(client, db_session):
    """Omitting the optional X-Organization-ID must return the global obligation, not crash."""
    org = bootstrap_org_user(client, email_prefix="obligation-no-org")

    SeedService.ensure_starter_obligations(db_session)
    db_session.commit()
    obligation = db_session.execute(select(Obligation).limit(1)).scalar_one_or_none()
    assert obligation is not None, "expected seeded starter obligations"

    # Authenticated, but deliberately no X-Organization-ID header.
    response = client.get(
        f"/api/v1/obligations/{obligation.id}",
        headers=org["headers"],
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["id"] == str(obligation.id)
    # Org-scoped state is simply absent when no org context was supplied.
    assert payload.get("organization_state") is None


def test_obligation_detail_with_org_header_still_returns_org_state(client, db_session):
    """The org-scoped path must keep working unchanged."""
    org = bootstrap_org_user(client, email_prefix="obligation-with-org")

    SeedService.ensure_starter_obligations(db_session)
    db_session.commit()
    obligation = db_session.execute(select(Obligation).limit(1)).scalar_one_or_none()
    assert obligation is not None

    response = client.get(
        f"/api/v1/obligations/{obligation.id}",
        headers=org["org_headers"],
    )
    assert response.status_code == 200, response.text
    assert response.json()["id"] == str(obligation.id)


def test_obligation_detail_rejects_malformed_org_header(client, db_session):
    """A malformed org header is a client error, not a crash."""
    org = bootstrap_org_user(client, email_prefix="obligation-bad-org")

    SeedService.ensure_starter_obligations(db_session)
    db_session.commit()
    obligation = db_session.execute(select(Obligation).limit(1)).scalar_one_or_none()
    assert obligation is not None

    headers = dict(org["headers"])
    headers["X-Organization-ID"] = "not-a-uuid"
    response = client.get(f"/api/v1/obligations/{obligation.id}", headers=headers)
    assert response.status_code == 400, response.text


def test_obligation_detail_unknown_org_header_is_404(client, db_session):
    """An unknown org id stays a 404 rather than falling through to the global read."""
    org = bootstrap_org_user(client, email_prefix="obligation-unknown-org")

    SeedService.ensure_starter_obligations(db_session)
    db_session.commit()
    obligation = db_session.execute(select(Obligation).limit(1)).scalar_one_or_none()
    assert obligation is not None

    headers = dict(org["headers"])
    headers["X-Organization-ID"] = str(uuid.uuid4())
    response = client.get(f"/api/v1/obligations/{obligation.id}", headers=headers)
    assert response.status_code == 404, response.text
