from __future__ import annotations

import uuid

from app.models.cloud_evidence_connector import CloudEvidenceConnector
from app.models.control import Control
from app.models.evidence_item import EvidenceItem
from app.models.finding_control_suggestion import CloudFindingControlMappingRule
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/cloud-connectors"


def _create_okta_connector(client, db_session, email_prefix: str):
    org = bootstrap_org_user(client, email_prefix=email_prefix)
    org_id = uuid.UUID(org["organization_id"])

    create = client.post(BASE, headers=org["org_headers"], json={"connector_type": "okta", "display_name": "Okta"})
    assert create.status_code == 201
    signing_secret = create.json()["signing_secret"]
    connector_id = uuid.UUID(create.json()["connector"]["id"])
    client.post(f"{BASE}/{connector_id}/activate", headers=org["org_headers"])

    control = Control(organization_id=org_id, title="Privileged access control", control_type="administrative", status="implemented")
    db_session.add(control)
    db_session.flush()
    db_session.add(
        CloudFindingControlMappingRule(
            organization_id=org_id,
            finding_category="iam_overly_broad",
            target_control_id=control.id,
            confidence="deterministic_partial",
            is_active=True,
        )
    )
    db_session.commit()

    webhook_token = db_session.get(CloudEvidenceConnector, connector_id).webhook_token
    return org, org_id, connector_id, control, signing_secret, webhook_token


def test_okta_verification_challenge_echoed(client, db_session):
    org, org_id, connector_id, control, signing_secret, webhook_token = _create_okta_connector(client, db_session, "okta-challenge")

    response = client.get(
        f"{BASE}/ingest/okta/{webhook_token}",
        headers={"x-okta-verification-challenge": "random-challenge-value"},
    )
    assert response.status_code == 200
    assert response.json() == {"verification": "random-challenge-value"}


def test_okta_events_rejected_without_matching_secret(client, db_session):
    org, org_id, connector_id, control, signing_secret, webhook_token = _create_okta_connector(client, db_session, "okta-nosecret")
    payload = {"eventType": "com.okta.event_hook", "data": {"events": []}}

    response = client.post(f"{BASE}/ingest/okta/{webhook_token}", json=payload, headers={"Authorization": "wrong-secret"})
    assert response.status_code == 401


def test_okta_events_signed_flow_to_evidence_and_suggestion(client, db_session):
    org, org_id, connector_id, control, signing_secret, webhook_token = _create_okta_connector(client, db_session, "okta-e2e")

    payload = {
        "eventType": "com.okta.event_hook",
        "data": {
            "events": [
                {
                    "uuid": "evt-uuid-1",
                    "eventType": "user.account.privilege.grant",
                    "severity": "WARN",
                    "displayMessage": "Admin privilege granted to user",
                    "target": [{"id": "00u123", "type": "User", "displayName": "Jane Doe"}],
                }
            ]
        },
    }
    response = client.post(f"{BASE}/ingest/okta/{webhook_token}", json=payload, headers={"Authorization": signing_secret})
    assert response.status_code == 202
    assert response.json()["findings_processed"] == 1

    evidence = (
        db_session.query(EvidenceItem)
        .filter(EvidenceItem.organization_id == org_id, EvidenceItem.source_import_tool == "cloud_connector_okta")
        .one()
    )
    assert "Admin privilege" in evidence.title
