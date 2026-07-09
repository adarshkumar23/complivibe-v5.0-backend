from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.compliance.services.webhook_service import WebhookService
from app.core.security import get_password_hash
from app.models.audit_engagement import AuditEngagement
from app.models.audit_log import AuditLog
from app.models.control import Control
from app.models.evidence_item import EvidenceItem
from app.models.membership import Membership
from app.models.offboarding_record import OffboardingRecord
from app.models.compliance_policy import CompliancePolicy
from app.models.risk import Risk
from app.models.role import Role
from app.models.task import Task
from app.models.user import User
from app.models.vendor import Vendor
from app.models.webhook_delivery import WebhookDelivery
from app.models.webhook_endpoint import WebhookEndpoint
from tests.helpers.auth_org import bootstrap_org_user, login_user, org_headers


WEBHOOKS_BASE = "/api/v1/compliance/webhook-endpoints"
OFFBOARDING_BASE = "/api/v1/compliance/offboarding"


def _create_active_user_with_role(db_session, org_id: str, *, email: str, role_name: str = "compliance_manager") -> User:
    role = db_session.execute(
        select(Role).where(
            Role.organization_id == uuid.UUID(org_id),
            Role.name == role_name,
        )
    ).scalar_one()
    user = User(
        email=email,
        full_name=email.split("@")[0],
        hashed_password=get_password_hash("Pass1234!@"),
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(
        Membership(
            organization_id=uuid.UUID(org_id),
            user_id=user.id,
            role_id=role.id,
            status="active",
            invited_by=None,
        )
    )
    db_session.commit()
    return user


def test_a82_webhook_endpoints_emit_signature_delivery_and_isolation(client, db_session, monkeypatch):
    org_a = bootstrap_org_user(client, email_prefix="a82-org-a")
    org_b = bootstrap_org_user(client, email_prefix="a82-org-b")

    # Create endpoint with valid event types.
    created = client.post(
        WEBHOOKS_BASE,
        headers=org_a["org_headers"],
        json={
            "url": "https://example.com/hooks/security",
            "name": "Security Hooks",
            "secret": "topsecret",
            "event_types": ["issue.created", "risk.critical"],
        },
    )
    assert created.status_code == 201
    endpoint_id = created.json()["id"]

    # Unknown event type rejected.
    invalid = client.post(
        WEBHOOKS_BASE,
        headers=org_a["org_headers"],
        json={
            "url": "https://example.com/hooks/invalid",
            "name": "Invalid",
            "secret": "topsecret",
            "event_types": ["issue.created", "made.up"],
        },
    )
    assert invalid.status_code == 422

    # Non-matching endpoint should not receive delivery.
    non_matching = client.post(
        WEBHOOKS_BASE,
        headers=org_a["org_headers"],
        json={
            "url": "https://example.com/hooks/non-matching",
            "name": "Non matching",
            "secret": "secret2",
            "event_types": ["deadline.overdue"],
        },
    )
    assert non_matching.status_code == 201

    emit = client.post(
        f"{WEBHOOKS_BASE}/test-emit",
        headers=org_a["org_headers"],
        json={
            "event_type": "issue.created",
            "test_payload": {"test": True, "id": "abc"},
        },
    )
    assert emit.status_code == 200
    deliveries = emit.json()
    assert len(deliveries) == 1
    delivery = deliveries[0]
    assert delivery["endpoint_id"] == endpoint_id

    # Signature and payload hash deterministic.
    assert delivery["signature"].startswith("sha256=")
    expected_hash = hashlib.sha256(json.dumps({"test": True, "id": "abc"}, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    assert delivery["payload_hash"] == expected_hash

    # Delivery stub has been replaced with real outbound HTTP delivery.
    service = WebhookService(db_session)

    class _SuccessResponse:
        status_code = 200

        def raise_for_status(self):
            return None

    with monkeypatch.context() as mp:
        mp.setattr("httpx.post", lambda *args, **kwargs: _SuccessResponse())
        updated = service.deliver(uuid.UUID(delivery["id"]))
        db_session.commit()

    assert updated.status == "delivered"
    assert updated.response_code == 200
    assert updated.error_message is None
    assert updated.attempts == 1

    audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.entity_id == uuid.UUID(delivery["id"]),
            AuditLog.action == "webhook.delivered",
        )
    ).scalar_one()
    assert audit is not None

    # Deactivate + soft delete guard.
    delete_active = client.delete(f"{WEBHOOKS_BASE}/{endpoint_id}", headers=org_a["org_headers"])
    assert delete_active.status_code == 422

    deactivated = client.post(f"{WEBHOOKS_BASE}/{endpoint_id}/deactivate", headers=org_a["org_headers"])
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    deleted = client.delete(f"{WEBHOOKS_BASE}/{endpoint_id}", headers=org_a["org_headers"])
    assert deleted.status_code == 200

    # Org isolation.
    list_org_b = client.get(WEBHOOKS_BASE, headers=org_b["org_headers"])
    assert list_org_b.status_code == 200
    assert all(row["organization_id"] == org_b["organization_id"] for row in list_org_b.json())


def test_webhook_endpoint_rejects_ssrf_targets(client):
    org = bootstrap_org_user(client, email_prefix="webhook-ssrf")

    for bad_url in [
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://127.0.0.1:8000/internal",
        "http://localhost/internal",
        "http://[::1]/internal",
        "http://2130706433/internal",
        "http://0177.0.0.1/internal",
    ]:
        created = client.post(
            WEBHOOKS_BASE,
            headers=org["org_headers"],
            json={
                "url": bad_url,
                "name": "Blocked",
                "secret": "topsecret",
                "event_types": ["issue.created"],
            },
        )
        assert created.status_code == 422, (bad_url, created.text)


def test_a83_offboarding_validate_run_transaction_and_guards(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a83-org")
    deactivated = _create_active_user_with_role(
        db_session,
        org["organization_id"],
        email="a83-deactivated@example.com",
        role_name="compliance_manager",
    )
    successor = _create_active_user_with_role(
        db_session,
        org["organization_id"],
        email="a83-successor@example.com",
        role_name="compliance_manager",
    )

    org_id = uuid.UUID(org["organization_id"])

    # Seed owned records for deactivated user.
    db_session.add(
        Risk(
            organization_id=org_id,
            title="Risk owned by deactivated user",
            description="desc",
            category="security",
            severity="high",
            owner_user_id=deactivated.id,
            created_by_user_id=uuid.UUID(org["user_id"]),
        )
    )
    db_session.add(
        Control(
            organization_id=org_id,
            title="Control owned by deactivated user",
            owner_user_id=deactivated.id,
        )
    )
    db_session.add(
        Task(
            organization_id=org_id,
            title="Open task owned by deactivated user",
            owner_user_id=deactivated.id,
            status="open",
        )
    )
    db_session.add(
        CompliancePolicy(
            organization_id=org_id,
            title="Policy owned by deactivated user",
            policy_type="security",
            status="active",
            owner_user_id=deactivated.id,
            version="1.0",
        )
    )
    db_session.add(
        Vendor(
            organization_id=org_id,
            name="Vendor owned by deactivated user",
            vendor_type="saas",
            owner_user_id=deactivated.id,
        )
    )
    db_session.add(
        AuditEngagement(
            organization_id=org_id,
            title="Audit with assigned auditors",
            audit_type="internal_readiness",
            scope_framework_ids=[],
            assigned_auditor_ids=[str(deactivated.id)],
            status="planning",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=7),
            created_by=uuid.UUID(org["user_id"]),
        )
    )
    db_session.commit()

    # validate_offboarding returns counts only, no data changes.
    preview = client.post(f"{OFFBOARDING_BASE}/validate/{deactivated.id}", headers=org["org_headers"])
    assert preview.status_code == 200
    preview_body = preview.json()
    assert preview_body["risks_to_reassign"] == 1
    assert preview_body["controls_to_reassign"] == 1
    assert preview_body["tasks_to_reassign"] == 1
    assert preview_body["policies_to_reassign"] == 1
    assert preview_body["vendors_to_reassign"] == 1
    assert preview_body["audit_engagements_to_reassign"] == 1

    still_owned = db_session.execute(
        select(Risk).where(Risk.organization_id == org_id, Risk.owner_user_id == deactivated.id)
    ).scalars().all()
    assert len(still_owned) == 1

    # require_successor_on_deactivate guard when successor missing.
    updated_cfg = client.patch(
        f"{OFFBOARDING_BASE}/configuration",
        headers=org["org_headers"],
        json={"require_successor_on_deactivate": True},
    )
    assert updated_cfg.status_code == 200

    missing_successor = client.post(
        f"{OFFBOARDING_BASE}/run",
        headers=org["org_headers"],
        json={"deactivated_user_id": str(deactivated.id)},
    )
    assert missing_successor.status_code == 422

    # self-successor blocked.
    same_user = client.post(
        f"{OFFBOARDING_BASE}/run",
        headers=org["org_headers"],
        json={"deactivated_user_id": str(deactivated.id), "successor_id": str(deactivated.id)},
    )
    assert same_user.status_code == 422

    # Execute offboarding transaction.
    run = client.post(
        f"{OFFBOARDING_BASE}/run",
        headers=org["org_headers"],
        json={"deactivated_user_id": str(deactivated.id), "successor_id": str(successor.id)},
    )
    assert run.status_code == 200
    body = run.json()
    assert body["total_reassigned"] == 6
    assert body["records_reassigned"]["risks"] == 1
    assert body["records_reassigned"]["tasks"] == 1

    # Reassignment checks.
    risk_rows = db_session.execute(select(Risk).where(Risk.organization_id == org_id)).scalars().all()
    assert all(row.owner_user_id == successor.id for row in risk_rows)

    task_rows = db_session.execute(select(Task).where(Task.organization_id == org_id)).scalars().all()
    assert all(row.owner_user_id == successor.id for row in task_rows)

    engagement = db_session.execute(select(AuditEngagement).where(AuditEngagement.organization_id == org_id)).scalar_one()
    assert str(successor.id) in list(engagement.assigned_auditor_ids or [])

    record = db_session.execute(
        select(OffboardingRecord).where(OffboardingRecord.organization_id == org_id, OffboardingRecord.id == uuid.UUID(body["id"]))
    ).scalar_one_or_none()
    assert record is not None
    assert record.total_reassigned == 6


def test_a83_offboarding_org_isolation_and_admin_only(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="a83-org-a")
    org_b = bootstrap_org_user(client, email_prefix="a83-org-b")

    deactivated = _create_active_user_with_role(
        db_session,
        org_a["organization_id"],
        email="a83-isolation-deactivated@example.com",
        role_name="compliance_manager",
    )
    successor = _create_active_user_with_role(
        db_session,
        org_a["organization_id"],
        email="a83-isolation-successor@example.com",
        role_name="compliance_manager",
    )

    # Admin-only: compliance_manager member in org A should be blocked.
    manager = _create_active_user_with_role(
        db_session,
        org_a["organization_id"],
        email="a83-manager@example.com",
        role_name="compliance_manager",
    )
    manager_token = login_user(client, manager.email)
    manager_headers = org_headers(manager_token, org_a["organization_id"])

    forbidden = client.post(f"{OFFBOARDING_BASE}/validate/{deactivated.id}", headers=manager_headers)
    assert forbidden.status_code == 403

    # Org isolation: org B admin cannot offboard org A user.
    wrong_org_headers = org_b["org_headers"]
    isolation = client.post(
        f"{OFFBOARDING_BASE}/run",
        headers=wrong_org_headers,
        json={"deactivated_user_id": str(deactivated.id), "successor_id": str(successor.id)},
    )
    assert isolation.status_code == 422


def test_webhook_delivery_retries_and_fails(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="webhook-fail")

    created = client.post(
        WEBHOOKS_BASE,
        headers=org["org_headers"],
        json={
                "url": "https://example.com/hooks/fail",
            "name": "Failing Hook",
            "secret": "secret",
            "event_types": ["issue.created"],
        },
    )
    assert created.status_code == 201
    endpoint_id = created.json()["id"]

    emit = client.post(
        f"{WEBHOOKS_BASE}/test-emit",
        headers=org["org_headers"],
        json={"event_type": "issue.created", "test_payload": {"foo": "bar"}},
    )
    assert emit.status_code == 200
    delivery_id = emit.json()[0]["id"]

    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: (_ for _ in ()).throw(Exception("boom")))
    monkeypatch.setattr("time.sleep", lambda *_: None)

    updated = WebhookService(db_session).deliver(uuid.UUID(delivery_id))
    db_session.commit()

    assert updated.status == "failed"
    assert updated.attempts == 3
    assert "boom" in (updated.error_message or "")

    audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.entity_id == uuid.UUID(delivery_id),
            AuditLog.action == "webhook.delivery_failed",
        )
    ).scalar_one()
    assert audit.after_json["attempts"] == 3


def test_webhook_delivery_trigger_endpoint(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="webhook-trigger")

    created = client.post(
        WEBHOOKS_BASE,
        headers=org["org_headers"],
        json={
                "url": "https://example.com/hooks/trigger",
            "name": "Trigger Hook",
            "secret": "secret",
            "event_types": ["risk.critical"],
        },
    )
    assert created.status_code == 201
    endpoint_id = created.json()["id"]

    emit = client.post(
        f"{WEBHOOKS_BASE}/test-emit",
        headers=org["org_headers"],
        json={"event_type": "risk.critical", "test_payload": {"severity": "high"}},
    )
    assert emit.status_code == 200
    delivery_id = emit.json()[0]["id"]

    class _CreatedResponse:
        status_code = 201

        def raise_for_status(self):
            return None

    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: _CreatedResponse())
    monkeypatch.setattr("time.sleep", lambda *_: None)

    trigger = client.post(
        f"{WEBHOOKS_BASE}/{endpoint_id}/deliveries/{delivery_id}/deliver",
        headers=org["org_headers"],
    )
    assert trigger.status_code == 200
    body = trigger.json()
    assert body["status"] == "delivered"
    assert body["response_code"] == 201
    assert body["attempts"] == 1

    audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.entity_id == uuid.UUID(delivery_id),
            AuditLog.action == "webhook.delivered",
        )
    ).scalar_one()
    assert audit is not None


def test_g4_all_six_domain_events_actually_emit_from_real_trigger_sites(client, db_session):
    """WebhookService.emit() was fully built (signing, delivery, SSRF protection) but the
    only real caller was the manual /test-emit endpoint -- none of the 6 advertised event
    types (control.failed, risk.critical, evidence.expired, deadline.overdue,
    issue.created, alert.triggered) ever fired from the real domain action they describe.
    This drives each real trigger site end-to-end through the actual API and asserts a
    WebhookDelivery row with the right event_type actually landed.
    """
    org = bootstrap_org_user(client, email_prefix="g4-six-events")
    owner_id = org["user_id"]

    endpoint = client.post(
        WEBHOOKS_BASE,
        headers=org["org_headers"],
        json={
            "url": "https://example.com/hooks/g4-all-events",
            "name": "All Events",
            "secret": "g4-secret",
            "event_types": [
                "control.failed",
                "risk.critical",
                "evidence.expired",
                "deadline.overdue",
                "issue.created",
                "alert.triggered",
            ],
        },
    )
    assert endpoint.status_code == 201
    endpoint_id = endpoint.json()["id"]

    def _deliveries_for(event_type: str) -> list:
        rows = db_session.execute(
            select(WebhookDelivery).where(
                WebhookDelivery.endpoint_id == uuid.UUID(endpoint_id),
                WebhookDelivery.event_type == event_type,
            )
        ).scalars().all()
        return rows

    # 1) control.failed -- PATCH a control's status to "failed".
    control = client.post(
        "/api/v1/controls",
        headers=org["org_headers"],
        json={"title": "G4 Control", "control_type": "policy", "criticality": "medium"},
    )
    assert control.status_code == 201
    control_id = control.json()["id"]
    patched = client.patch(
        f"/api/v1/controls/{control_id}",
        headers=org["org_headers"],
        json={"status": "failed"},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "failed"
    control_deliveries = _deliveries_for("control.failed")
    assert len(control_deliveries) == 1
    assert control_deliveries[0].payload["control_id"] == control_id

    # 2) risk.critical -- create a risk with likelihood*impact=25 (critical band).
    risk = client.post(
        "/api/v1/risks",
        headers=org["org_headers"],
        json={"title": "G4 Risk", "category": "operational", "likelihood": 5, "impact": 5},
    )
    assert risk.status_code == 201
    assert risk.json()["severity"] == "critical"
    risk_deliveries = _deliveries_for("risk.critical")
    assert len(risk_deliveries) == 1
    assert risk_deliveries[0].payload["risk_id"] == risk.json()["id"]

    # 3) evidence.expired -- create evidence already past valid_until, then list it (the
    # list/detail endpoints are what actually detect + flip freshness_status to expired).
    # Created with a *future* valid_until so freshness_status starts as "current"/
    # "expiring_soon" (creating it already-expired short-circuits the transition-detection
    # in _is_expired, which intentionally skips rows already marked expired to avoid
    # re-emitting on every list call). Then backdate valid_until directly, mirroring an
    # evidence item that goes stale after it was accepted -- the real-world case this
    # detection exists for.
    future = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    evidence = client.post(
        "/api/v1/evidence",
        headers=org["org_headers"],
        json={"title": "G4 Evidence", "evidence_type": "policy_document", "valid_until": future},
    )
    assert evidence.status_code == 201
    evidence_row = db_session.query(EvidenceItem).filter(EvidenceItem.id == uuid.UUID(evidence.json()["id"])).one()
    evidence_row.valid_until = datetime.now(UTC) - timedelta(days=1)
    db_session.commit()

    listed = client.get("/api/v1/evidence", headers=org["org_headers"])
    assert listed.status_code == 200
    evidence_deliveries = _deliveries_for("evidence.expired")
    assert len(evidence_deliveries) == 1
    assert evidence_deliveries[0].payload["evidence_id"] == evidence.json()["id"]

    # 4) deadline.overdue -- create a deadline already past due, then run evaluate-due.
    deadline = client.post(
        "/api/v1/compliance/deadlines",
        headers=org["org_headers"],
        json={
            "title": "G4 Deadline",
            "deadline_type": "custom",
            "due_date": (date.today() - timedelta(days=1)).isoformat(),
            "owner_user_id": owner_id,
            "reminder_days_before": 7,
        },
    )
    assert deadline.status_code == 201
    evaluated = client.post(
        "/api/v1/compliance/deadlines/evaluate-due",
        headers=org["org_headers"],
        json={"dry_run": False},
    )
    assert evaluated.status_code == 200
    assert evaluated.json()["overdue_marked"] >= 1
    deadline_deliveries = _deliveries_for("deadline.overdue")
    assert len(deadline_deliveries) == 1
    assert deadline_deliveries[0].payload["deadline_id"] == deadline.json()["id"]

    # 5) issue.created -- create an issue via the real API.
    issue = client.post(
        "/api/v1/compliance/issues",
        headers=org["org_headers"],
        json={
            "title": "G4 Issue",
            "description": "Something broke",
            "issue_type": "operational_failure",
            "severity": "high",
            "owner_id": owner_id,
        },
    )
    assert issue.status_code == 201
    issue_deliveries = _deliveries_for("issue.created")
    assert len(issue_deliveries) == 1
    assert issue_deliveries[0].payload["issue_id"] == issue.json()["id"]

    # 6) alert.triggered -- a control-monitoring rule with action_type="create_alert" that
    # matches, evaluated live (not dry_run).
    definition = client.post(
        "/api/v1/compliance/monitoring/definitions",
        headers=org["org_headers"],
        json={
            "control_id": control_id,
            "name": "G4 Monitoring Definition",
            "monitoring_type": "manual_check",
            "check_frequency": "weekly",
            "owner_user_id": owner_id,
        },
    )
    assert definition.status_code == 201
    definition_id = definition.json()["id"]
    from app.models.control_monitoring_definition import ControlMonitoringDefinition

    def_row = db_session.query(ControlMonitoringDefinition).filter(
        ControlMonitoringDefinition.id == uuid.UUID(definition_id)
    ).one()
    def_row.next_check_due_at = datetime.now(UTC) - timedelta(days=3)
    db_session.commit()

    rule = client.post(
        "/api/v1/compliance/monitoring/rules",
        headers=org["org_headers"],
        json={
            "name": "G4 Alert Rule",
            "rule_type": "overdue_check",
            "condition_json": {"days_overdue_threshold": 1},
            "action_type": "create_alert",
            "action_config_json": {"severity": "high"},
        },
    )
    assert rule.status_code == 201

    rule_eval = client.post(
        "/api/v1/compliance/monitoring/rules/evaluate",
        headers=org["org_headers"],
        json={"dry_run": False},
    )
    assert rule_eval.status_code == 200
    alert_deliveries = _deliveries_for("alert.triggered")
    assert len(alert_deliveries) == 1
    assert alert_deliveries[0].payload["control_id"] == control_id
