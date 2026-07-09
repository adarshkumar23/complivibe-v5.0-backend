from __future__ import annotations

from tests.helpers.auth_org import bootstrap_org_user

RISK_SCORES_BASE = "/api/v1/compliance/risk-scores"
DATA_ASSETS_BASE = "/api/v1/data-observability/assets"


def test_compute_entity_succeeds_end_to_end_for_data_asset(client, db_session):
    """G3 item 5: the compute-entity endpoint's Pydantic schema has always accepted
    entity_type="data_asset", but the DB CHECK constraint on entity_risk_scores
    (0095_entity_level_risk_scoring.py) only allowed ('vendor','asset','business_unit',
    'framework') -- so a data_asset compute-entity call passed schema validation and
    then hit an unhandled IntegrityError (500) on INSERT against real Postgres.
    Migration 0285 widens the CHECK constraint to include 'data_asset'. This test
    exercises the full application-layer path (schema + service); since the test
    suite runs against SQLite (which does not enforce this Postgres CHECK constraint
    at all, and the ORM model doesn't declare it either), it cannot reproduce the
    Postgres-only 500 directly -- but it proves entity_type="data_asset" is accepted
    by the schema and the service computes/persists a real score end-to-end, which
    is exactly what the widened CHECK constraint must not block on real Postgres.
    """
    org = bootstrap_org_user(client, email_prefix="g3-ers-data-asset")
    headers = org["org_headers"]
    owner_id = org["user_id"]

    asset_resp = client.post(
        DATA_ASSETS_BASE,
        headers=headers,
        json={
            "name": "G3 Data Asset",
            "asset_type": "database",
            "owner_id": owner_id,
            "status": "active",
        },
    )
    assert asset_resp.status_code == 201, asset_resp.text
    asset_id = asset_resp.json()["id"]

    compute_resp = client.post(
        f"{RISK_SCORES_BASE}/compute-entity",
        headers=headers,
        json={"entity_type": "data_asset", "entity_id": asset_id},
    )
    assert compute_resp.status_code == 201, compute_resp.text
    body = compute_resp.json()
    assert body["entity_type"] == "data_asset"
    assert body["entity_id"] == asset_id
    assert body["score_band"] in {"critical", "high", "medium", "low", "none"}
