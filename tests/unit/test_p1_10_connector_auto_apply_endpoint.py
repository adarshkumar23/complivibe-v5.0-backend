"""P1.10 regression: auto_apply_deterministic_mappings must be settable via the
API. Previously the flag existed on the model and drove ingest behavior but had
no create field and no update endpoint, so it could only be changed by a direct
DB write (defaulting to False forever via the API).
"""
from __future__ import annotations

from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/cloud-connectors"


def _create(client):
    org = bootstrap_org_user(client, email_prefix="conn-autoapply")
    r = client.post(
        BASE,
        headers=org["org_headers"],
        json={"connector_type": "aws", "display_name": "aws", "provider_config_json": {}},
    )
    assert r.status_code == 201, r.text
    return org, r.json()["connector"]["id"]


def test_auto_apply_deterministic_mappings_is_settable_via_api(client, db_session):
    org, connector_id = _create(client)
    h = org["org_headers"]

    assert client.get(f"{BASE}/{connector_id}", headers=h).json()["auto_apply_deterministic_mappings"] is False

    patched = client.patch(
        f"{BASE}/{connector_id}", headers=h, json={"auto_apply_deterministic_mappings": True}
    )
    assert patched.status_code == 200, f"PATCH should update the flag, got {patched.status_code}: {patched.text}"
    assert patched.json()["auto_apply_deterministic_mappings"] is True

    # Persisted.
    assert client.get(f"{BASE}/{connector_id}", headers=h).json()["auto_apply_deterministic_mappings"] is True
