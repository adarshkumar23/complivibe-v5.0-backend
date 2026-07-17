"""Coverage for the org risk-settings endpoints (app/api/v1/risk_settings.py).

Zero prior test references. Exercises GET default weights, PUT upsert with the
weights-must-sum-to-1.0 validation, risks:write / risks:read permission
enforcement, and org-scoping isolation of the singleton settings row.
"""

from __future__ import annotations

from app.compliance.services.risk_scoring_service import RiskScoringService
from tests.helpers.auth_org import add_org_member, bootstrap_org_user

SETTINGS = "/api/v1/compliance/risk-settings"


def test_get_returns_defaults_then_put_upserts(client, db_session):
    org = bootstrap_org_user(client, email_prefix="rs-happy")
    h = org["org_headers"]

    # no row yet -> service defaults
    got = client.get(SETTINGS, headers=h)
    assert got.status_code == 200, got.text
    assert got.json() == {
        "financial_weight": float(RiskScoringService.DEFAULT_FINANCIAL_WEIGHT),
        "brand_weight": float(RiskScoringService.DEFAULT_BRAND_WEIGHT),
        "operational_weight": float(RiskScoringService.DEFAULT_OPERATIONAL_WEIGHT),
    }

    # upsert (create) valid weights summing to 1.0
    put = client.put(
        SETTINGS,
        headers=h,
        json={"financial_weight": 0.5, "brand_weight": 0.2, "operational_weight": 0.3},
    )
    assert put.status_code == 200, put.text
    assert put.json() == {"financial_weight": 0.5, "brand_weight": 0.2, "operational_weight": 0.3}

    # GET now reflects the persisted row
    got2 = client.get(SETTINGS, headers=h)
    assert got2.json() == {"financial_weight": 0.5, "brand_weight": 0.2, "operational_weight": 0.3}

    # upsert (update) existing row
    upd = client.put(
        SETTINGS,
        headers=h,
        json={"financial_weight": 0.34, "brand_weight": 0.33, "operational_weight": 0.33},
    )
    assert upd.status_code == 200, upd.text
    assert client.get(SETTINGS, headers=h).json()["financial_weight"] == 0.34


def test_put_rejects_weights_not_summing_to_one(client, db_session):
    org = bootstrap_org_user(client, email_prefix="rs-sum")
    r = client.put(
        SETTINGS,
        headers=org["org_headers"],
        json={"financial_weight": 0.5, "brand_weight": 0.5, "operational_weight": 0.5},
    )
    assert r.status_code == 422, r.text
    assert "sum to 1.0" in r.json()["detail"]


def test_get_requires_risks_read_and_put_requires_write(client, db_session):
    org = bootstrap_org_user(client, email_prefix="rs-perm")
    # readonly has risks:read but NOT risks:write
    ro = add_org_member(db_session, client, org["organization_id"], "rs-readonly@example.com", role_name="readonly")

    # can read
    assert client.get(SETTINGS, headers=ro).status_code == 200
    # cannot write -> 403
    w = client.put(
        SETTINGS,
        headers=ro,
        json={"financial_weight": 0.5, "brand_weight": 0.2, "operational_weight": 0.3},
    )
    assert w.status_code == 403, w.text


def test_settings_org_scoped(client, db_session):
    # org A sets custom weights; org B still sees defaults (singleton is per-org).
    org_a = bootstrap_org_user(client, email_prefix="rs-a")
    client.put(
        SETTINGS,
        headers=org_a["org_headers"],
        json={"financial_weight": 0.6, "brand_weight": 0.1, "operational_weight": 0.3},
    ).raise_for_status()

    org_b = bootstrap_org_user(client, email_prefix="rs-b")
    got_b = client.get(SETTINGS, headers=org_b["org_headers"])
    assert got_b.status_code == 200
    assert got_b.json() == {
        "financial_weight": float(RiskScoringService.DEFAULT_FINANCIAL_WEIGHT),
        "brand_weight": float(RiskScoringService.DEFAULT_BRAND_WEIGHT),
        "operational_weight": float(RiskScoringService.DEFAULT_OPERATIONAL_WEIGHT),
    }
