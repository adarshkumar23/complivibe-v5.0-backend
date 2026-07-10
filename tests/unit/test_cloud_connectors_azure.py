from __future__ import annotations

import uuid

from app.integrations.cloud_connectors.connector_service import CloudConnectorService
from app.models.cloud_evidence_connector import CloudEvidenceConnector
from app.models.control import Control
from app.models.control_test_run import ControlTestRun
from app.models.evidence_item import EvidenceItem
from app.models.finding_control_suggestion import CloudFindingControlMappingRule
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/cloud-connectors"


def _create_azure_connector(client, db_session, email_prefix: str):
    org = bootstrap_org_user(client, email_prefix=email_prefix)
    org_id = uuid.UUID(org["organization_id"])

    create = client.post(BASE, headers=org["org_headers"], json={"connector_type": "azure", "display_name": "Azure Policy"})
    assert create.status_code == 201
    signing_secret = create.json()["signing_secret"]
    connector_id = uuid.UUID(create.json()["connector"]["id"])
    client.post(f"{BASE}/{connector_id}/activate", headers=org["org_headers"])

    control = Control(organization_id=org_id, title="Storage encryption control", control_type="technical", status="implemented")
    db_session.add(control)
    db_session.flush()
    db_session.add(
        CloudFindingControlMappingRule(
            organization_id=org_id,
            finding_category="encryption_missing",
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


def test_azure_subscription_validation_handshake(client, db_session):
    org, org_id, connector_id, control, signing_secret, webhook_token = _create_azure_connector(client, db_session, "azure-handshake")

    validation_payload = [
        {
            "id": "val-1",
            "eventType": "Microsoft.EventGrid.SubscriptionValidationEvent",
            "data": {"validationCode": "abc123", "validationUrl": "https://example.com/validate?code=abc123"},
        }
    ]
    response = client.post(f"{BASE}/ingest/azure/{webhook_token}", json=validation_payload)
    assert response.status_code == 200
    assert response.json() == [{"validationResponse": "abc123"}]


def test_azure_events_rejected_without_shared_secret(client, db_session):
    org, org_id, connector_id, control, signing_secret, webhook_token = _create_azure_connector(client, db_session, "azure-nosecret")

    events = [
        {
            "id": "evt-1",
            "eventType": "Microsoft.PolicyInsights.PolicyStateChanged",
            "subject": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/acct1",
            "data": {
                "complianceState": "NonCompliant",
                "policyDefinitionId": "/providers/Microsoft.Authorization/policyDefinitions/require-encryption",
                "policyAssignmentId": "/subscriptions/sub/providers/Microsoft.Authorization/policyAssignments/enc-policy",
                "resourceId": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/acct1",
            },
        }
    ]
    response = client.post(f"{BASE}/ingest/azure/{webhook_token}", json=events)
    assert response.status_code == 401


def test_azure_events_signed_flow_to_evidence_control_and_monitoring(client, db_session):
    org, org_id, connector_id, control, signing_secret, webhook_token = _create_azure_connector(client, db_session, "azure-e2e")

    events = [
        {
            "id": "evt-2",
            "eventType": "Microsoft.PolicyInsights.PolicyStateChanged",
            "subject": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/acct2",
            "data": {
                "complianceState": "NonCompliant",
                "policyDefinitionId": "/providers/Microsoft.Authorization/policyDefinitions/require-encryption",
                "policyAssignmentId": "/subscriptions/sub/providers/Microsoft.Authorization/policyAssignments/enc-policy",
                "resourceId": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/acct2",
            },
        }
    ]
    response = client.post(
        f"{BASE}/ingest/azure/{webhook_token}",
        json=events,
        headers={"X-CompliVibe-Shared-Secret": signing_secret},
    )
    assert response.status_code == 200
    assert response.json()["findings_processed"] == 1

    evidence = (
        db_session.query(EvidenceItem)
        .filter(EvidenceItem.organization_id == org_id, EvidenceItem.source_import_tool == "cloud_connector_azure")
        .one()
    )
    assert "NonCompliant" in evidence.title or "noncompliant" in evidence.title.lower()

    run = db_session.query(ControlTestRun).filter(ControlTestRun.organization_id == org_id, ControlTestRun.control_id == control.id).one()
    assert run.result == "failed"
    assert run.execution_source == "cloud_connector"
