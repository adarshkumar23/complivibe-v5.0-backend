from datetime import UTC, datetime
from tests.helpers.auth_org import bootstrap_org_user

ASSETS_BASE = "/api/v1/data-observability/assets"
LINEAGE_BASE = "/api/v1/data-observability/lineage"
ACCESS_BASE = "/api/v1/data-observability/access"


def test_verify_unique_actors_counts_external_machine_actors(client):
    org = bootstrap_org_user(client, email_prefix="partD-actors")
    ingest_key = "partD-ingest-key-12345"

    configured = client.post(
        f"{LINEAGE_BASE}/openmetadata/configure",
        headers=org["org_headers"],
        json={
            "base_url": "https://openmetadata.example.com",
            "jwt_token": "dummy-token",
            "org_api_key": ingest_key,
        },
    )
    assert configured.status_code == 200, configured.text

    asset = client.post(
        ASSETS_BASE,
        headers=org["org_headers"],
        json={"name": "PartD Asset", "asset_type": "database", "owner_id": org["user_id"]},
    )
    print("ASSET:", asset.status_code, asset.json())
    assert asset.status_code == 201, asset.text
    asset_id = asset.json()["id"]

    now = datetime.now(UTC)

    def _ingest(actor_id=None, actor_external=None):
        resp = client.post(
            f"{ACCESS_BASE}/events",
            headers={"X-CompliVibe-Key": ingest_key},
            json={
                "data_asset_id": asset_id,
                "actor_id": actor_id,
                "actor_external": actor_external,
                "access_type": "read",
                "access_result": "success",
                "access_time": now.isoformat(),
            },
        )
        assert resp.status_code == 201, resp.text

    _ingest(actor_id=org["user_id"])
    _ingest(actor_external="etl-pipeline-1")
    _ingest(actor_external="etl-pipeline-2")

    summary = client.get(f"{ACCESS_BASE}/summary", headers=org["org_headers"])
    print("SUMMARY:", summary.status_code, summary.json())
    assert summary.status_code == 200
    body = summary.json()
    assert body["unique_actors"] == 3, (
        f"BUG: unique_actors ignores actor_external, expected 3 (1 human + 2 machine), got {body['unique_actors']}"
    )
