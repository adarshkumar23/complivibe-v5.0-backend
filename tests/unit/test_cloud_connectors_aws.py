from __future__ import annotations

import hashlib
import hmac
import json
import uuid

from app.integrations.cloud_connectors.connector_service import CloudConnectorService
from app.models.control import Control
from app.models.control_test_run import ControlTestRun
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.finding_control_suggestion import CloudFindingControlMappingRule, FindingControlSuggestion
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/cloud-connectors"

AWS_EVENTBRIDGE_PAYLOAD = {
    "version": "0",
    "id": "abcd-1234",
    "detail-type": "Security Hub Findings - Imported",
    "source": "aws.securityhub",
    "account": "123456789012",
    "time": "2026-07-10T00:00:00Z",
    "region": "us-east-1",
    "detail": {
        "findings": [
            {
                "Id": "arn:aws:securityhub:us-east-1:123456789012:subscription/aws-foundational/v/1.0.0/S3.1/finding/aaaa",
                "Title": "S3 bucket X is publicly readable",
                "Description": "An S3 bucket allows public read access.",
                "Severity": {"Label": "CRITICAL"},
                "Types": ["Software and Configuration Checks/AWS Security Best Practices"],
                "Resources": [{"Id": "arn:aws:s3:::example-bucket", "Type": "AwsS3Bucket"}],
                "GeneratorId": "aws-foundational-security-best-practices/v/1.0.0/S3.1",
            }
        ]
    },
}


def _sign(secret: str, raw_body: bytes) -> str:
    return hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()


def _setup_connector_with_rule(client, db_session, email_prefix: str):
    org = bootstrap_org_user(client, email_prefix=email_prefix)
    org_id = uuid.UUID(org["organization_id"])

    create = client.post(
        BASE,
        headers=org["org_headers"],
        json={"connector_type": "aws", "display_name": "AWS Security Hub"},
    )
    assert create.status_code == 201
    connector_id = uuid.UUID(create.json()["connector"]["id"])
    signing_secret = create.json()["signing_secret"]

    activate = client.post(f"{BASE}/{connector_id}/activate", headers=org["org_headers"])
    assert activate.status_code == 200

    control = Control(organization_id=org_id, title="S3 public access control", control_type="technical", status="implemented")
    db_session.add(control)
    db_session.flush()

    rule = CloudFindingControlMappingRule(
        organization_id=org_id,
        finding_category="s3_public_bucket",
        target_control_id=control.id,
        confidence="deterministic_exact",
        is_active=True,
    )
    db_session.add(rule)

    from app.models.cloud_evidence_connector import CloudEvidenceConnector

    connector_row = db_session.get(CloudEvidenceConnector, connector_id)
    connector_row.auto_apply_deterministic_mappings = True
    db_session.commit()

    return org, org_id, connector_id, control, signing_secret


def test_aws_finding_rejected_with_bad_signature(client, db_session):
    from app.models.cloud_evidence_connector import CloudEvidenceConnector

    org, org_id, connector_id, control, signing_secret = _setup_connector_with_rule(client, db_session, "aws-badsig")
    webhook_token = db_session.get(CloudEvidenceConnector, connector_id).webhook_token
    raw_body = json.dumps(AWS_EVENTBRIDGE_PAYLOAD).encode()

    response = client.post(
        f"{BASE}/ingest/aws/{webhook_token}",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-CompliVibe-Signature": "sha256=deadbeef"},
    )
    assert response.status_code == 401


def test_aws_finding_signed_flows_to_evidence_control_and_monitoring(client, db_session):
    org, org_id, connector_id, control, signing_secret = _setup_connector_with_rule(client, db_session, "aws-e2e")

    from app.models.cloud_evidence_connector import CloudEvidenceConnector

    connector_row = db_session.get(CloudEvidenceConnector, connector_id)
    webhook_token = connector_row.webhook_token

    raw_body = json.dumps(AWS_EVENTBRIDGE_PAYLOAD).encode()
    signature = _sign(signing_secret, raw_body)

    response = client.post(
        f"{BASE}/ingest/aws/{webhook_token}",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-CompliVibe-Signature": f"sha256={signature}"},
    )
    assert response.status_code == 202
    assert response.json()["findings_processed"] == 1

    evidence = (
        db_session.query(EvidenceItem)
        .filter(EvidenceItem.organization_id == org_id, EvidenceItem.source_import_tool == "cloud_connector_aws")
        .one()
    )
    assert "publicly readable" in evidence.title

    suggestion = db_session.query(FindingControlSuggestion).filter(FindingControlSuggestion.organization_id == org_id).one()
    assert suggestion.status == "applied"
    assert suggestion.suggested_control_id == control.id

    link = (
        db_session.query(EvidenceControlLink)
        .filter(EvidenceControlLink.organization_id == org_id, EvidenceControlLink.control_id == control.id)
        .one()
    )
    assert link.link_status == "active"

    run = db_session.query(ControlTestRun).filter(ControlTestRun.organization_id == org_id, ControlTestRun.control_id == control.id).one()
    assert run.result == "failed"
    assert run.execution_source == "cloud_connector"

    health = client.get(f"{BASE}/{connector_id}/health", headers=org["org_headers"])
    assert health.json()["hours_since_last_event"] == 0

    # Replay of the same finding is deduped, not reprocessed twice.
    replay = client.post(
        f"{BASE}/ingest/aws/{webhook_token}",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-CompliVibe-Signature": f"sha256={signature}"},
    )
    assert replay.status_code == 202
    evidence_count = (
        db_session.query(EvidenceItem)
        .filter(EvidenceItem.organization_id == org_id, EvidenceItem.source_import_tool == "cloud_connector_aws")
        .count()
    )
    assert evidence_count == 1
