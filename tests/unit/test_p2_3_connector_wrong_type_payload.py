"""P2.3 (deep-verification finding): a valid-JSON but wrong-top-level-type
payload (e.g. a JSON array instead of an object) with VALID credentials must be
rejected with a clean 400, not crash the GitHub/Okta parsers with an unhandled
AttributeError -> 500. Azure already guards this with isinstance(events, list).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid

from app.models.cloud_evidence_connector import CloudEvidenceConnector
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/cloud-connectors"


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _create(client, db_session, connector_type):
    org = bootstrap_org_user(client, email_prefix=f"p23-{connector_type}")
    r = client.post(BASE, headers=org["org_headers"],
                    json={"connector_type": connector_type, "display_name": connector_type, "provider_config_json": {}})
    assert r.status_code == 201, r.text
    cid = r.json()["connector"]["id"]
    secret = r.json()["signing_secret"]
    client.post(f"{BASE}/{cid}/activate", headers=org["org_headers"])
    token = db_session.get(CloudEvidenceConnector, uuid.UUID(cid)).webhook_token
    return token, secret


def test_github_wrong_type_payload_is_400_not_500(client, db_session):
    token, secret = _create(client, db_session, "github")
    body = json.dumps([1, 2, 3]).encode()  # valid JSON, wrong type
    resp = client.post(
        f"{BASE}/ingest/github/{token}",
        content=body,
        headers={"Content-Type": "application/json", "X-GitHub-Event": "secret_scanning_alert",
                 "X-GitHub-Delivery": str(uuid.uuid4()), "X-Hub-Signature-256": f"sha256={_sign(secret, body)}"},
    )
    assert resp.status_code == 400, f"expected clean 400, got {resp.status_code}"


def test_okta_wrong_type_payload_is_400_not_500(client, db_session):
    token, secret = _create(client, db_session, "okta")
    body = json.dumps([1, 2, 3]).encode()
    resp = client.post(
        f"{BASE}/ingest/okta/{token}",
        content=body,
        headers={"Content-Type": "application/json", "Authorization": secret},
    )
    assert resp.status_code == 400, f"expected clean 400, got {resp.status_code}"
