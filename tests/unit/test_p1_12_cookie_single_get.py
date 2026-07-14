"""P1.12 regression: GET /privacy/cookies/{id} must return the single cookie.
The path only had PATCH bound, so a GET returned 405 Method Not Allowed.
"""
from __future__ import annotations

from tests.helpers.auth_org import bootstrap_org_user


def test_cookie_single_get(client, db_session):
    org = bootstrap_org_user(client, email_prefix="cookie-get")
    h = org["org_headers"]

    created = client.post(
        "/api/v1/privacy/cookies",
        headers=h,
        json={"name": "_ga", "domain": "example.com", "category": "analytics"},
    )
    assert created.status_code == 201, created.text
    cookie_id = created.json()["id"]

    got = client.get(f"/api/v1/privacy/cookies/{cookie_id}", headers=h)
    assert got.status_code == 200, f"single-GET should return 200, got {got.status_code}"
    assert got.json()["id"] == cookie_id
    assert got.json()["name"] == "_ga"

    # Unknown id -> 404 (not 405).
    missing = client.get("/api/v1/privacy/cookies/00000000-0000-0000-0000-000000000000", headers=h)
    assert missing.status_code == 404
