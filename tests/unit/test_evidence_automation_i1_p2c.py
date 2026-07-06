import json
import uuid

from app.models.audit_log import AuditLog
from app.models.control import Control
from app.models.evidence_automation_rule import EvidenceAutomationRule
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.permission import Permission


def _register(client, email: str, org_name: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Pass1234!@", "organization_name": org_name},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str, org_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organization-ID"] = org_id
    return headers


def _org_id(client, token: str) -> str:
    response = client.get("/api/v1/organizations/me", headers=_headers(token))
    assert response.status_code == 200
    return response.json()[0]["id"]


def _create_control(client, token: str, org_id: str, title: str) -> str:
    response = client.post(
        "/api/v1/controls",
        headers=_headers(token, org_id),
        json={"title": title, "control_type": "technical", "criticality": "high"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_i1_permissions_seeded_and_rule_crud(client, db_session):
    token = _register(client, "i1-owner-a@example.com", "I1 Org A")
    org_id = _org_id(client, token)
    control_id = _create_control(client, token, org_id, "I1 evidence control")

    permission_keys = {row.key for row in db_session.query(Permission).all()}
    assert {
        "evidence_automation_rules:read",
        "evidence_automation_rules:write",
        "evidence_automation_ingest:webhook",
        "evidence_automation_ingest:email",
        "evidence_automation_ingest:form",
    }.issubset(permission_keys)

    create_response = client.post(
        "/api/v1/evidence-automation/rules",
        headers=_headers(token, org_id),
        json={
            "trigger_source": "webhook",
            "trigger_config": {"match": {"event.kind": "build_passed"}, "required_fields": ["artifact.sha256"]},
            "target_control_id": control_id,
            "evidence_type": "technical_test",
            "transform_template": json.dumps(
                {
                    "title": "Build pass {{event.id}}",
                    "description": "Pipeline {{pipeline.name}} completed",
                    "external_reference_url": "{{links.report}}",
                    "metadata": {"artifact_sha": "{{artifact.sha256}}"},
                }
            ),
            "is_active": True,
        },
    )
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()
    rule_id = created["id"]
    assert created["trigger_source"] == "webhook"
    assert created["target_control_id"] == control_id

    list_response = client.get("/api/v1/evidence-automation/rules", headers=_headers(token, org_id))
    assert list_response.status_code == 200
    assert any(row["id"] == rule_id for row in list_response.json())

    patch_response = client.patch(
        f"/api/v1/evidence-automation/rules/{rule_id}",
        headers=_headers(token, org_id),
        json={"is_active": False, "evidence_type": "attestation"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["is_active"] is False
    assert patch_response.json()["evidence_type"] == "attestation"

    rule_row = (
        db_session.query(EvidenceAutomationRule)
        .filter(EvidenceAutomationRule.organization_id == uuid.UUID(org_id), EvidenceAutomationRule.id == uuid.UUID(rule_id))
        .one()
    )
    assert rule_row.is_active is False
    assert rule_row.evidence_type == "attestation"

    audit_actions = {
        row.action
        for row in db_session.query(AuditLog)
        .filter(
            AuditLog.organization_id == uuid.UUID(org_id),
            AuditLog.entity_type == "evidence_automation_rule",
        )
        .all()
    }
    assert "evidence_automation_rule.created" in audit_actions
    assert "evidence_automation_rule.updated" in audit_actions


def test_i1_ingest_webhook_creates_evidence_in_existing_tables(client, db_session):
    token = _register(client, "i1-owner-b@example.com", "I1 Org B")
    org_id = _org_id(client, token)
    control_id = _create_control(client, token, org_id, "I1 webhook control")

    create_rule_response = client.post(
        "/api/v1/evidence-automation/rules",
        headers=_headers(token, org_id),
        json={
            "trigger_source": "webhook",
            "trigger_config": {"match": {"event.kind": "deploy"}, "required_fields": ["event.id", "links.report"]},
            "target_control_id": control_id,
            "evidence_type": "technical_test",
            "transform_template": json.dumps(
                {
                    "title": "Deployment {{event.id}} succeeded",
                    "description": "Env {{event.environment}}",
                    "external_reference_url": "{{links.report}}",
                    "valid_until_days": 30,
                    "metadata": {"run_id": "{{event.id}}", "env": "{{event.environment}}"},
                }
            ),
        },
    )
    assert create_rule_response.status_code == 201

    ingest_response = client.post(
        "/api/v1/evidence-automation/inbound/webhook",
        headers=_headers(token, org_id),
        json={
            "payload": {
                "event": {"kind": "deploy", "id": "run-145", "environment": "prod"},
                "links": {"report": "https://example.internal/reports/run-145"},
            }
        },
    )
    assert ingest_response.status_code == 200, ingest_response.text
    body = ingest_response.json()
    assert body["source"] == "webhook"
    assert body["created_count"] == 1
    assert body["matched_rule_count"] == 1
    assert body["errors"] == []
    evidence_id = body["evidence_item_ids"][0]

    evidence_row = (
        db_session.query(EvidenceItem)
        .filter(EvidenceItem.organization_id == uuid.UUID(org_id), EvidenceItem.id == uuid.UUID(evidence_id))
        .one()
    )
    assert evidence_row.source == "automation_webhook"
    assert evidence_row.evidence_type == "technical_test"
    assert evidence_row.title == "Deployment run-145 succeeded"
    assert evidence_row.metadata_json["run_id"] == "run-145"

    link_row = (
        db_session.query(EvidenceControlLink)
        .filter(
            EvidenceControlLink.organization_id == uuid.UUID(org_id),
            EvidenceControlLink.evidence_item_id == evidence_row.id,
            EvidenceControlLink.control_id == uuid.UUID(control_id),
            EvidenceControlLink.link_status == "active",
        )
        .one()
    )
    assert link_row.confidence == "imported"

    evidence_audit_actions = {
        row.action
        for row in db_session.query(AuditLog)
        .filter(AuditLog.organization_id == uuid.UUID(org_id), AuditLog.entity_id == evidence_row.id)
        .all()
    }
    assert "evidence.created" in evidence_audit_actions

    ingest_audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.organization_id == uuid.UUID(org_id),
            AuditLog.action == "evidence_automation_ingest.webhook",
        )
        .first()
    )
    assert ingest_audit is not None


def test_i1_ingest_handles_bad_template_without_crashing(client):
    token = _register(client, "i1-owner-c@example.com", "I1 Org C")
    org_id = _org_id(client, token)

    rule_response = client.post(
        "/api/v1/evidence-automation/rules",
        headers=_headers(token, org_id),
        json={
            "trigger_source": "email",
            "trigger_config": {"required_fields": ["subject"]},
            "evidence_type": "attestation",
            "transform_template": "{\"title\": 123}",
        },
    )
    assert rule_response.status_code == 400

    valid_rule = client.post(
        "/api/v1/evidence-automation/rules",
        headers=_headers(token, org_id),
        json={
            "trigger_source": "email",
            "trigger_config": {"required_fields": ["subject"]},
            "evidence_type": "attestation",
            "transform_template": "{\"title\": \"Evidence {{subject}}\"}",
        },
    )
    assert valid_rule.status_code == 201
    rule_id = valid_rule.json()["id"]

    broken_patch = client.patch(
        f"/api/v1/evidence-automation/rules/{rule_id}",
        headers=_headers(token, org_id),
        json={"transform_template": "{\"title\": 123}"},
    )
    assert broken_patch.status_code == 400

    ingest_response = client.post(
        "/api/v1/evidence-automation/inbound/email-parse",
        headers=_headers(token, org_id),
        json={"payload": {"missing_subject": "ignored"}},
    )
    assert ingest_response.status_code == 200
    body = ingest_response.json()
    assert body["created_count"] == 0
    assert body["matched_rule_count"] == 0
    assert body["skipped_rule_count"] >= 1
    assert body["errors"] == []
