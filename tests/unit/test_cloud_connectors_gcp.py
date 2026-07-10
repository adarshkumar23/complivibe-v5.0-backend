from __future__ import annotations

import base64
import json
import time
import uuid

from authlib.jose import JsonWebKey, jwt

from app.integrations.cloud_connectors import signature_verification
from app.models.cloud_evidence_connector import CloudEvidenceConnector
from app.models.control import Control
from app.models.evidence_item import EvidenceItem
from app.models.finding_control_suggestion import CloudFindingControlMappingRule
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/cloud-connectors"
SERVICE_ACCOUNT_EMAIL = "svc-scc@my-project.iam.gserviceaccount.com"


def _key() -> JsonWebKey:
    return JsonWebKey.generate_key("RSA", 2048, is_private=True, options={"kid": "test-key-1"})


def _make_id_token(key: JsonWebKey, *, audience: str, email: str = SERVICE_ACCOUNT_EMAIL, email_verified: bool = True) -> str:
    now = int(time.time())
    payload = {
        "iss": "https://accounts.google.com",
        "aud": audience,
        "exp": now + 300,
        "iat": now,
        "email": email,
        "email_verified": email_verified,
    }
    return jwt.encode({"alg": "RS256", "kid": key.as_dict()["kid"]}, payload, key).decode()


def _scc_envelope(*, finding_name: str, category: str = "PUBLIC_BUCKET_ACL", severity: str = "CRITICAL") -> dict:
    finding = {
        "finding": {
            "name": finding_name,
            "category": category,
            "severity": severity,
            "resourceName": "//storage.googleapis.com/projects/my-project/buckets/my-bucket",
            "description": "Bucket is publicly accessible.",
        }
    }
    data_b64 = base64.b64encode(json.dumps(finding).encode()).decode()
    return {"message": {"data": data_b64, "messageId": "msg-1"}, "subscription": "projects/my-project/subscriptions/complivibe-push"}


def _create_gcp_connector(client, db_session, email_prefix: str):
    org = bootstrap_org_user(client, email_prefix=email_prefix)
    org_id = uuid.UUID(org["organization_id"])

    create = client.post(
        BASE,
        headers=org["org_headers"],
        json={
            "connector_type": "gcp",
            "display_name": "GCP SCC",
            "provider_config_json": {"service_account_email": SERVICE_ACCOUNT_EMAIL},
        },
    )
    assert create.status_code == 201
    assert create.json()["signing_secret"] is None
    connector_id = uuid.UUID(create.json()["connector"]["id"])
    client.post(f"{BASE}/{connector_id}/activate", headers=org["org_headers"])

    control = Control(organization_id=org_id, title="GCS bucket public access control", control_type="technical", status="implemented")
    db_session.add(control)
    db_session.flush()
    db_session.add(
        CloudFindingControlMappingRule(
            organization_id=org_id,
            finding_category="s3_public_bucket",
            target_control_id=control.id,
            confidence="deterministic_partial",
            is_active=True,
        )
    )
    db_session.commit()

    webhook_token = db_session.get(CloudEvidenceConnector, connector_id).webhook_token
    return org, org_id, connector_id, webhook_token


def test_gcp_finding_rejected_without_bearer_token(client, db_session):
    org, org_id, connector_id, webhook_token = _create_gcp_connector(client, db_session, "gcp-nobearer")
    response = client.post(f"{BASE}/ingest/gcp/{webhook_token}", json=_scc_envelope(finding_name="finding-1"))
    assert response.status_code == 401


def test_gcp_finding_rejected_with_wrong_service_account(client, db_session, monkeypatch):
    org, org_id, connector_id, webhook_token = _create_gcp_connector(client, db_session, "gcp-wrongsvc")
    key = _key()
    monkeypatch.setattr(signature_verification, "_fetch_google_jwks", lambda: {"keys": [key.as_dict(is_private=False)]})

    audience = webhook_token
    token = _make_id_token(key, audience=audience, email="someone-else@other-project.iam.gserviceaccount.com")

    response = client.post(
        f"{BASE}/ingest/gcp/{webhook_token}",
        json=_scc_envelope(finding_name="finding-2"),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_gcp_finding_signed_flows_to_evidence_and_suggestion(client, db_session, monkeypatch):
    org, org_id, connector_id, webhook_token = _create_gcp_connector(client, db_session, "gcp-e2e")
    key = _key()
    monkeypatch.setattr(signature_verification, "_fetch_google_jwks", lambda: {"keys": [key.as_dict(is_private=False)]})

    audience = webhook_token
    token = _make_id_token(key, audience=audience)

    response = client.post(
        f"{BASE}/ingest/gcp/{webhook_token}",
        json=_scc_envelope(finding_name="organizations/123/sources/456/findings/abc"),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 202

    evidence = (
        db_session.query(EvidenceItem)
        .filter(EvidenceItem.organization_id == org_id, EvidenceItem.source_import_tool == "cloud_connector_gcp")
        .one()
    )
    assert "PUBLIC_BUCKET_ACL" in evidence.title
