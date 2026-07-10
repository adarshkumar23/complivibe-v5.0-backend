from __future__ import annotations

import hashlib
import hmac
import json
import uuid

from app.models.cloud_evidence_connector import CloudEvidenceConnector
from app.models.audit_log import AuditLog
from app.models.evidence_item import EvidenceItem
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/cloud-connectors"


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _create_connector(client, connector_type: str, email_prefix: str, provider_config_json=None):
    org = bootstrap_org_user(client, email_prefix=email_prefix)
    create = client.post(
        BASE,
        headers=org["org_headers"],
        json={
            "connector_type": connector_type,
            "display_name": connector_type,
            "provider_config_json": provider_config_json or {},
        },
    )
    assert create.status_code == 201
    connector_id = create.json()["connector"]["id"]
    signing_secret = create.json()["signing_secret"]
    client.post(f"{BASE}/{connector_id}/activate", headers=org["org_headers"])
    return org, connector_id, signing_secret


# ---------------------------------------------------------------------------
# Fix 1: request body size limit
# ---------------------------------------------------------------------------


def test_aws_oversized_payload_rejected_with_413(client, db_session):
    org, connector_id, signing_secret = _create_connector(client, "aws", "hardening-aws-size")
    webhook_token = db_session.get(CloudEvidenceConnector, uuid.UUID(connector_id)).webhook_token

    huge_description = "A" * (2 * 1024 * 1024)  # 2MB, over the 1MB limit
    payload = {
        "detail": {
            "findings": [
                {
                    "Id": f"oversized-{uuid.uuid4()}",
                    "Title": "Oversized test",
                    "Description": huge_description,
                    "Severity": {"Label": "LOW"},
                    "Types": [],
                    "Resources": [],
                }
            ]
        }
    }
    body = json.dumps(payload).encode()
    response = client.post(
        f"{BASE}/ingest/aws/{webhook_token}",
        content=body,
        headers={"Content-Type": "application/json", "X-CompliVibe-Signature": f"sha256={_sign(signing_secret, body)}"},
    )
    assert response.status_code == 413

    count = db_session.query(EvidenceItem).filter(EvidenceItem.title == "Oversized test").count()
    assert count == 0


def test_github_oversized_payload_rejected_with_413(client, db_session):
    org, connector_id, signing_secret = _create_connector(client, "github", "hardening-github-size")
    webhook_token = db_session.get(CloudEvidenceConnector, uuid.UUID(connector_id)).webhook_token

    payload = {
        "action": "created",
        "alert": {"number": 1, "secret_type": "x", "secret_type_display_name": "X" * (2 * 1024 * 1024)},
        "repository": {"full_name": "acme/r"},
    }
    body = json.dumps(payload).encode()
    response = client.post(
        f"{BASE}/ingest/github/{webhook_token}",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "secret_scanning_alert",
            "X-GitHub-Delivery": str(uuid.uuid4()),
            "X-Hub-Signature-256": f"sha256={_sign(signing_secret, body)}",
        },
    )
    assert response.status_code == 413


def test_azure_oversized_payload_rejected_with_413(client, db_session):
    org, connector_id, signing_secret = _create_connector(client, "azure", "hardening-azure-size")
    webhook_token = db_session.get(CloudEvidenceConnector, uuid.UUID(connector_id)).webhook_token

    events = [
        {
            "id": "evt-1",
            "eventType": "Microsoft.PolicyInsights.PolicyStateChanged",
            "subject": "x",
            "data": {"complianceState": "NonCompliant", "extra": "A" * (2 * 1024 * 1024)},
        }
    ]
    body = json.dumps(events).encode()
    response = client.post(
        f"{BASE}/ingest/azure/{webhook_token}",
        content=body,
        headers={"Content-Type": "application/json", "X-CompliVibe-Shared-Secret": signing_secret},
    )
    assert response.status_code == 413


def test_okta_oversized_payload_rejected_with_413(client, db_session):
    org, connector_id, signing_secret = _create_connector(client, "okta", "hardening-okta-size")
    webhook_token = db_session.get(CloudEvidenceConnector, uuid.UUID(connector_id)).webhook_token

    payload = {"eventType": "com.okta.event_hook", "data": {"events": [{"uuid": "u1", "displayMessage": "A" * (2 * 1024 * 1024)}]}}
    body = json.dumps(payload).encode()
    response = client.post(
        f"{BASE}/ingest/okta/{webhook_token}",
        content=body,
        headers={"Content-Type": "application/json", "Authorization": signing_secret},
    )
    assert response.status_code == 413


def test_gcp_oversized_payload_rejected_with_413_via_content_length(client, db_session):
    org, connector_id, signing_secret = _create_connector(
        client, "gcp", "hardening-gcp-size", provider_config_json={"service_account_email": "svc@proj.iam.gserviceaccount.com"}
    )
    webhook_token = db_session.get(CloudEvidenceConnector, uuid.UUID(connector_id)).webhook_token

    body = json.dumps({"message": {"data": "A" * (2 * 1024 * 1024), "messageId": "m1"}}).encode()
    # The Content-Length pre-check runs before anything else (including auth), so an
    # oversized body is rejected with 413 even without a bearer token.
    response = client.post(
        f"{BASE}/ingest/gcp/{webhook_token}",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413


# ---------------------------------------------------------------------------
# Fix 2: secret rotation
# ---------------------------------------------------------------------------


def test_rotate_secret_invalidates_old_secret_and_new_one_works_github(client, db_session):
    org, connector_id, old_secret = _create_connector(client, "github", "hardening-rotate-github")
    webhook_token = db_session.get(CloudEvidenceConnector, uuid.UUID(connector_id)).webhook_token

    rotate = client.post(f"{BASE}/{connector_id}/rotate-secret", headers=org["org_headers"])
    assert rotate.status_code == 200
    new_secret = rotate.json()["signing_secret"]
    assert new_secret != old_secret

    payload = {"action": "created", "alert": {"number": 1, "secret_type": "x"}, "repository": {"full_name": "acme/r"}}
    body = json.dumps(payload).encode()
    headers_common = {"Content-Type": "application/json", "X-GitHub-Event": "secret_scanning_alert", "X-GitHub-Delivery": str(uuid.uuid4())}

    # Old secret must be rejected immediately.
    old_sig = _sign(old_secret, body)
    r_old = client.post(f"{BASE}/ingest/github/{webhook_token}", content=body, headers={**headers_common, "X-Hub-Signature-256": old_sig})
    assert r_old.status_code == 401

    # New secret must work.
    new_sig = _sign(new_secret, body)
    r_new = client.post(
        f"{BASE}/ingest/github/{webhook_token}",
        content=body,
        headers={**headers_common, "X-GitHub-Delivery": str(uuid.uuid4()), "X-Hub-Signature-256": new_sig},
    )
    assert r_new.status_code == 202

    # Audit log recorded the rotation.
    logs = db_session.query(AuditLog).filter(
        AuditLog.entity_id == uuid.UUID(connector_id), AuditLog.action == "cloud_connector.secret_rotated"
    ).all()
    assert len(logs) == 1
    assert logs[0].actor_user_id is not None


def test_rotate_secret_invalidates_old_secret_azure_shared_secret(client, db_session):
    org, connector_id, old_secret = _create_connector(client, "azure", "hardening-rotate-azure")
    webhook_token = db_session.get(CloudEvidenceConnector, uuid.UUID(connector_id)).webhook_token

    rotate = client.post(f"{BASE}/{connector_id}/rotate-secret", headers=org["org_headers"])
    assert rotate.status_code == 200
    new_secret = rotate.json()["signing_secret"]

    events = [{
        "id": "evt-rotate-1",
        "eventType": "Microsoft.PolicyInsights.PolicyStateChanged",
        "subject": "x",
        "data": {"complianceState": "NonCompliant", "policyDefinitionId": "d", "policyAssignmentId": "a", "resourceId": "r"},
    }]

    r_old = client.post(f"{BASE}/ingest/azure/{webhook_token}", json=events, headers={"X-CompliVibe-Shared-Secret": old_secret})
    assert r_old.status_code == 401

    r_new = client.post(f"{BASE}/ingest/azure/{webhook_token}", json=events, headers={"X-CompliVibe-Shared-Secret": new_secret})
    assert r_new.status_code == 200


def test_rotate_secret_rejected_for_gcp_connector(client, db_session):
    org, connector_id, old_secret = _create_connector(
        client, "gcp", "hardening-rotate-gcp", provider_config_json={"service_account_email": "svc@proj.iam.gserviceaccount.com"}
    )
    assert old_secret is None

    rotate = client.post(f"{BASE}/{connector_id}/rotate-secret", headers=org["org_headers"])
    assert rotate.status_code == 422
