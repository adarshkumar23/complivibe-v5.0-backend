from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, timedelta

from sqlalchemy import select

from app.compliance.services.webhook_service import WebhookService
from app.core.security import get_password_hash
from app.models.audit_engagement import AuditEngagement
from app.models.control import Control
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


def test_a82_webhook_endpoints_emit_signature_delivery_stub_and_isolation(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="a82-org-a")
    org_b = bootstrap_org_user(client, email_prefix="a82-org-b")

    # Create endpoint with valid event types.
    created = client.post(
        WEBHOOKS_BASE,
        headers=org_a["org_headers"],
        json={
            "url": "https://example.test/hooks/security",
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
            "url": "https://example.test/hooks/invalid",
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
            "url": "https://example.test/hooks/non-matching",
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

    # Delivery stub: skipped and no HTTP implementation.
    service = WebhookService(db_session)
    updated = service.deliver(uuid.UUID(delivery["id"]))
    db_session.commit()
    assert updated.status == "skipped"
    assert updated.error_message is not None
    assert "not yet implemented" in updated.error_message

    with open("app/compliance/services/webhook_service.py", "r", encoding="utf-8") as f:
        source = f.read().lower()
    assert "httpx" not in source

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


