from __future__ import annotations

import hashlib
import hmac
import json
import uuid

from app.models.cloud_evidence_connector import CloudEvidenceConnector
from app.models.control import Control
from app.models.control_test_run import ControlTestRun
from app.models.evidence_item import EvidenceItem
from app.models.finding_control_suggestion import CloudFindingControlMappingRule
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/cloud-connectors"

SECRET_SCANNING_PAYLOAD = {
    "action": "created",
    "alert": {"number": 7, "secret_type": "aws_access_key_id", "secret_type_display_name": "AWS Access Key", "state": "open"},
    "repository": {"full_name": "acme/webapp"},
}


def _sign(secret: str, raw_body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()


def _create_github_connector(client, db_session, email_prefix: str):
    org = bootstrap_org_user(client, email_prefix=email_prefix)
    org_id = uuid.UUID(org["organization_id"])

    create = client.post(BASE, headers=org["org_headers"], json={"connector_type": "github", "display_name": "GitHub"})
    assert create.status_code == 201
    signing_secret = create.json()["signing_secret"]
    connector_id = uuid.UUID(create.json()["connector"]["id"])
    client.post(f"{BASE}/{connector_id}/activate", headers=org["org_headers"])

    control = Control(organization_id=org_id, title="Secret management control", control_type="technical", status="implemented")
    db_session.add(control)
    db_session.flush()
    db_session.add(
        CloudFindingControlMappingRule(
            organization_id=org_id,
            finding_category="secret_scanning",
            target_control_id=control.id,
            confidence="deterministic_exact",
            is_active=True,
        )
    )
    connector_row = db_session.get(CloudEvidenceConnector, connector_id)
    connector_row.auto_apply_deterministic_mappings = True
    db_session.commit()

    webhook_token = connector_row.webhook_token
    return org, org_id, connector_id, control, signing_secret, webhook_token


def test_github_webhook_rejected_with_bad_signature(client, db_session):
    org, org_id, connector_id, control, signing_secret, webhook_token = _create_github_connector(client, db_session, "github-badsig")
    raw_body = json.dumps(SECRET_SCANNING_PAYLOAD).encode()

    response = client.post(
        f"{BASE}/ingest/github/{webhook_token}",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=deadbeef",
            "X-GitHub-Event": "secret_scanning_alert",
            "X-GitHub-Delivery": "delivery-1",
        },
    )
    assert response.status_code == 401


def test_github_secret_scanning_alert_signed_flows_to_evidence_control_and_monitoring(client, db_session):
    org, org_id, connector_id, control, signing_secret, webhook_token = _create_github_connector(client, db_session, "github-e2e")
    raw_body = json.dumps(SECRET_SCANNING_PAYLOAD).encode()
    signature = _sign(signing_secret, raw_body)

    response = client.post(
        f"{BASE}/ingest/github/{webhook_token}",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": signature,
            "X-GitHub-Event": "secret_scanning_alert",
            "X-GitHub-Delivery": "delivery-2",
        },
    )
    assert response.status_code == 202
    assert response.json()["findings_processed"] == 1

    evidence = (
        db_session.query(EvidenceItem)
        .filter(EvidenceItem.organization_id == org_id, EvidenceItem.source_import_tool == "cloud_connector_github")
        .one()
    )
    assert "AWS Access Key" in evidence.title

    run = db_session.query(ControlTestRun).filter(ControlTestRun.organization_id == org_id, ControlTestRun.control_id == control.id).one()
    assert run.result == "failed"


def test_github_ignores_unactionable_event_types(client, db_session):
    org, org_id, connector_id, control, signing_secret, webhook_token = _create_github_connector(client, db_session, "github-ignore")
    payload = {"action": "opened", "repository": {"full_name": "acme/webapp"}}
    raw_body = json.dumps(payload).encode()
    signature = _sign(signing_secret, raw_body)

    response = client.post(
        f"{BASE}/ingest/github/{webhook_token}",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": signature,
            "X-GitHub-Event": "issues",
            "X-GitHub-Delivery": "delivery-3",
        },
    )
    assert response.status_code == 202
    assert response.json()["status"] == "ignored"
