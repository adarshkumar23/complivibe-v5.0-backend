"""Coverage for the carbon-accounting router (app/api/v1/carbon_accounting.py).

The existing suite (test_carbon_accounting_t33.py) proves the X-CompliVibe-Key
ingest path, scope3/period validation, in-place correction, and dashboard
insights. This file adds the parts it does NOT cover:

  * RBAC enforcement on the two *session-authenticated* endpoints -- the ingest
    endpoint uses an API key (no RBAC), but POST /api-key requires
    ``carbon_accounting:write`` and GET /dashboard requires
    ``carbon_accounting:read``. Only owner/admin/compliance_manager hold these;
    a ``readonly`` member must be rejected with 403.
  * A completely missing (not merely wrong) X-CompliVibe-Key header on ingest.
  * Org-scoping of the dashboard: one org's readings never leak into another
    org's dashboard, and an ingest key is bound to exactly one org.
"""

from __future__ import annotations

from tests.helpers.auth_org import add_org_member, bootstrap_org_user

API_KEY = "/api/v1/carbon-accounting/api-key"
READINGS = "/api/v1/carbon-accounting/readings"
DASHBOARD = "/api/v1/carbon-accounting/dashboard"


def _provision_key(client, org_headers: dict[str, str]) -> str:
    r = client.post(API_KEY, headers=org_headers)
    assert r.status_code == 200, r.text
    return r.json()["api_key"]


def _ingest(client, ingest_key: str, *, scope: str, value: str, source: str) -> None:
    r = client.post(
        READINGS,
        headers={"X-CompliVibe-Key": ingest_key},
        json={
            "scope": scope,
            "source": source,
            "period_start": "2026-03-01",
            "period_end": "2026-03-31",
            "value": value,
            "unit": "tCO2e",
        },
    )
    assert r.status_code == 201, r.text


# ---------------------------------------------------------------------------
# RBAC on the session-authenticated endpoints (readonly lacks both perms)
# ---------------------------------------------------------------------------


def test_dashboard_requires_carbon_accounting_read(client, db_session):
    org = bootstrap_org_user(client, email_prefix="carbon-cov-dashperm")
    readonly = add_org_member(
        db_session, client, org["organization_id"], "carbon-cov-ro-read@example.com", role_name="readonly"
    )
    r = client.get(DASHBOARD, headers=readonly)
    assert r.status_code == 403, r.text


def test_api_key_provision_requires_carbon_accounting_write(client, db_session):
    org = bootstrap_org_user(client, email_prefix="carbon-cov-keyperm")
    readonly = add_org_member(
        db_session, client, org["organization_id"], "carbon-cov-ro-write@example.com", role_name="readonly"
    )
    r = client.post(API_KEY, headers=readonly)
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# API-key auth edge: a totally absent header is rejected (not a 500), distinct
# from the existing "wrong key" test which sends a present-but-invalid value.
# ---------------------------------------------------------------------------


def test_ingest_missing_key_header_rejected(client):
    r = client.post(
        READINGS,
        json={
            "scope": "scope1",
            "source": "utility-meter",
            "period_start": "2026-03-01",
            "period_end": "2026-03-31",
            "value": "1",
            "unit": "tCO2e",
        },
    )
    assert r.status_code == 401, r.text
    assert r.json()["detail"] == "Invalid API key"


# ---------------------------------------------------------------------------
# Org-scoping: an ingest key writes only into its own org, and one org's
# dashboard never reflects another org's readings.
# ---------------------------------------------------------------------------


def test_dashboard_is_org_scoped_across_ingest_keys(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="carbon-cov-orga")
    org_b = bootstrap_org_user(client, email_prefix="carbon-cov-orgb")

    key_a = _provision_key(client, org_a["org_headers"])
    _provision_key(client, org_b["org_headers"])  # org B has its own key, but ingests nothing

    _ingest(client, key_a, scope="scope1", value="500", source="meter-a")

    # Org A sees its own reading.
    dash_a = client.get(DASHBOARD, headers=org_a["org_headers"])
    assert dash_a.status_code == 200, dash_a.text
    body_a = dash_a.json()
    assert body_a["reading_count"] == 1
    assert body_a["totals_by_scope"] == {"scope1": "500.0000"}

    # Org B, despite having provisioned its own key, sees nothing from org A.
    dash_b = client.get(DASHBOARD, headers=org_b["org_headers"])
    assert dash_b.status_code == 200, dash_b.text
    body_b = dash_b.json()
    assert body_b["reading_count"] == 0
    assert body_b["totals_by_scope"] == {}
