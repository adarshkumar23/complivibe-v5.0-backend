from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import inspect

from app.compliance.services.breach_notification_service import BreachNotificationService
from app.models.breach_notification import BreachNotification
from app.models.dpa_agreement import DPAAgreement
from app.models.email_outbox import EmailOutbox
from app.models.subprocessor import Subprocessor
from app.privacy.services.dpa_service import DPAService
from tests.helpers.auth_org import bootstrap_org_user

DPA_BASE = "/api/v1/privacy/dpas"
ISSUES_BASE = "/api/v1/compliance/issues"
BREACH_BASE = "/api/v1/compliance/breach-notifications"
ROPA_BASE = "/api/v1/privacy/ropa"


def _create_issue(client, headers: dict[str, str], owner_id: str, issue_type: str = "security_incident") -> dict:
    response = client.post(
        ISSUES_BASE,
        headers=headers,
        json={
            "title": "Breach issue",
            "description": "Potential personal data breach",
            "issue_type": issue_type,
            "severity": "high",
            "source_type": "manual",
            "owner_id": owner_id,
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_activity(client, headers: dict[str, str], owner_id: str, **overrides) -> dict:
    payload = {
        "name": "DPA linked activity",
        "description": "Personal data processing",
        "purpose": "Service operations",
        "legal_basis": "contract",
        "data_categories": ["personal_data"],
        "special_categories": [],
        "data_subject_types": ["customers"],
        "retention_period": "1 year",
        "recipients": ["internal"],
        "international_transfers": True,
        "status": "active",
        "risk_level": "medium",
        "owner_id": owner_id,
        "linked_data_asset_ids": [],
        "linked_subprocessor_ids": [],
    }
    payload.update(overrides)
    response = client.post(f"{ROPA_BASE}/activities", headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def _create_vendor(client, headers: dict[str, str], owner_id: str, **overrides) -> dict:
    payload = {
        "name": "DPA Vendor",
        "vendor_type": "software",
        "owner_user_id": owner_id,
        "risk_tier": "not_assessed",
        "status": "active",
        "data_access": True,
        "processes_personal_data": True,
        "sub_processor": False,
    }
    payload.update(overrides)
    response = client.post("/api/v1/compliance/vendors", headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def _create_dpa(client, headers: dict[str, str], owner_id: str, **overrides) -> dict:
    payload = {
        "counterparty_name": "Acme Processor",
        "counterparty_type": "processor",
        "status": "pending",
        "owner_id": owner_id,
        "governing_regulation": ["gdpr"],
        "renewal_notice_days": 30,
        "processing_activity_ids": [],
    }
    payload.update(overrides)
    response = client.post(DPA_BASE, headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def test_d92_dpa_tracking(client, db_session):
    org = bootstrap_org_user(client, email_prefix="d92-org")
    org_b = bootstrap_org_user(client, email_prefix="d92-org-b")

    # Create DPA with all allowed counterparty types.
    for counterparty_type in ("processor", "sub_processor", "joint_controller", "controller"):
        created = _create_dpa(
            client,
            org["org_headers"],
            org["user_id"],
            counterparty_name=f"{counterparty_type}-cp",
            counterparty_type=counterparty_type,
        )
        assert created["counterparty_type"] == counterparty_type

    dpa = _create_dpa(client, org["org_headers"], org["user_id"], counterparty_name="Main DPA")

    # Valid transitions.
    to_active = client.post(
        f"{DPA_BASE}/{dpa['id']}/status",
        headers=org["org_headers"],
        json={"new_status": "active"},
    )
    assert to_active.status_code == 200
    assert to_active.json()["status"] == "active"

    to_expired = client.post(
        f"{DPA_BASE}/{dpa['id']}/status",
        headers=org["org_headers"],
        json={"new_status": "expired"},
    )
    assert to_expired.status_code == 200
    assert to_expired.json()["status"] == "expired"

    # Invalid transition.
    invalid = client.post(
        f"{DPA_BASE}/{dpa['id']}/status",
        headers=org["org_headers"],
        json={"new_status": "under_review"},
    )
    assert invalid.status_code == 422

    # Terminal transition guard.
    term = _create_dpa(client, org["org_headers"], org["user_id"], counterparty_name="Terminal")
    terminate = client.post(
        f"{DPA_BASE}/{term['id']}/status",
        headers=org["org_headers"],
        json={"new_status": "terminated"},
    )
    assert terminate.status_code == 200
    blocked = client.post(
        f"{DPA_BASE}/{term['id']}/status",
        headers=org["org_headers"],
        json={"new_status": "active"},
    )
    assert blocked.status_code == 422

    # Link processing activity appends JSONB list.
    activity = _create_activity(client, org["org_headers"], org["user_id"])
    linked = client.post(
        f"{DPA_BASE}/{dpa['id']}/link-activity",
        headers=org["org_headers"],
        json={"activity_id": activity["id"]},
    )
    assert linked.status_code == 200
    assert activity["id"] in linked.json()["processing_activity_ids"]

    # Expiry sweep updates status and queues reminders.
    sweep_target = _create_dpa(
        client,
        org["org_headers"],
        org["user_id"],
        counterparty_name="Soon expiring",
        status="active",
        expiry_date=(date.today() + timedelta(days=5)).isoformat(),
    )
    expired_target = _create_dpa(
        client,
        org["org_headers"],
        org["user_id"],
        counterparty_name="Already expired",
        status="active",
        expiry_date=(date.today() - timedelta(days=1)).isoformat(),
    )

    sweep = DPAService(db_session).run_expiry_sweep(org_id=uuid.UUID(org["organization_id"]))
    db_session.commit()
    assert sweep["expiring_soon"] >= 1
    assert sweep["expired"] >= 1

    expired_row = db_session.get(DPAAgreement, uuid.UUID(expired_target["id"]))
    assert expired_row is not None
    assert expired_row.status == "expired"

    reminders = (
        db_session.query(EmailOutbox)
        .filter(
            EmailOutbox.organization_id == uuid.UUID(org["organization_id"]),
            EmailOutbox.event_type == "dpa.expiry_notice",
        )
        .count()
    )
    assert reminders >= 1

    # DPA summary missing_dpa_count.
    sp = Subprocessor(
        organization_id=uuid.UUID(org["organization_id"]),
        name="No DPA subprocessor",
        service_description="Processes data",
        data_types_processed=["email"],
        legal_basis="contract",
        geographic_locations=["DE"],
        data_transfer_mechanism="not_applicable",
        dpa_status="pending",
        controller_type="processor",
        risk_level="medium",
        status="active",
        created_by=uuid.UUID(org["user_id"]),
        deleted_at=None,
    )
    db_session.add(sp)
    db_session.commit()

    summary = client.get(f"{DPA_BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    assert summary.json()["missing_dpa_count"] >= 1

    # Soft delete only from terminated.
    not_terminated_delete = client.delete(f"{DPA_BASE}/{sweep_target['id']}", headers=org["org_headers"])
    assert not_terminated_delete.status_code == 422

    terminated_delete = client.delete(f"{DPA_BASE}/{term['id']}", headers=org["org_headers"])
    assert terminated_delete.status_code == 204

    # Org isolation.
    foreign = client.get(f"{DPA_BASE}/{dpa['id']}", headers=org_b["org_headers"])
    assert foreign.status_code == 404


def test_d92_dpa_update_status_transition_enforced(client, db_session):
    org = bootstrap_org_user(client, email_prefix="d92-update-transition")

    dpa = _create_dpa(client, org["org_headers"], org["user_id"], counterparty_name="Transition Guard")
    assert dpa["status"] == "pending"

    # Direct status update via PATCH must respect transition rules.
    bad_patch = client.patch(
        f"{DPA_BASE}/{dpa['id']}",
        headers=org["org_headers"],
        json={"status": "expired"},
    )
    assert bad_patch.status_code == 422
    assert "transition" in bad_patch.json()["detail"].lower()

    # Valid transitions still work through the dedicated endpoint.
    to_active = client.post(
        f"{DPA_BASE}/{dpa['id']}/status",
        headers=org["org_headers"],
        json={"new_status": "active"},
    )
    assert to_active.status_code == 200
    assert to_active.json()["status"] == "active"


def test_d92_dpa_create_and_patch_reject_foreign_related_records(client):
    org = bootstrap_org_user(client, email_prefix="d92-dpa-scope-a")
    org_b = bootstrap_org_user(client, email_prefix="d92-dpa-scope-b")
    foreign_vendor = _create_vendor(client, org_b["org_headers"], org_b["user_id"], name="Foreign DPA Vendor")
    foreign_activity = _create_activity(client, org_b["org_headers"], org_b["user_id"], name="Foreign DPA Activity")

    create_foreign_vendor = client.post(
        DPA_BASE,
        headers=org["org_headers"],
        json={
            "counterparty_name": "Foreign Vendor DPA",
            "counterparty_type": "processor",
            "vendor_id": foreign_vendor["id"],
            "status": "pending",
            "owner_id": org["user_id"],
            "governing_regulation": ["gdpr"],
            "renewal_notice_days": 30,
            "processing_activity_ids": [],
        },
    )
    assert create_foreign_vendor.status_code == 404
    assert create_foreign_vendor.json()["detail"] == "Vendor not found"

    dpa = _create_dpa(client, org["org_headers"], org["user_id"], counterparty_name="Scoped DPA")
    patch_foreign_activity = client.patch(
        f"{DPA_BASE}/{dpa['id']}",
        headers=org["org_headers"],
        json={"processing_activity_ids": [foreign_activity["id"]]},
    )
    assert patch_foreign_activity.status_code == 404
    assert patch_foreign_activity.json()["detail"] == "Processing activity not found"

    own_activity = _create_activity(client, org["org_headers"], org["user_id"], name="Own DPA Activity")
    patch_own_activity = client.patch(
        f"{DPA_BASE}/{dpa['id']}",
        headers=org["org_headers"],
        json={"processing_activity_ids": [own_activity["id"]]},
    )
    assert patch_own_activity.status_code == 200
    assert patch_own_activity.json()["processing_activity_ids"] == [own_activity["id"]]


def test_d89_breach_notification_extension(client, db_session):
    org = bootstrap_org_user(client, email_prefix="d89-org")

    # Migration columns exist.
    columns = {col["name"] for col in inspect(db_session.bind).get_columns("breach_notifications")}
    assert "data_subjects_affected_count" in columns
    assert "special_category_data_involved" in columns
    assert "article33_notification_text" in columns
    assert "article34_required" in columns
    assert "subjects_notification_text" in columns
    assert "dpa_reference_number" in columns

    issue = _create_issue(client, org["org_headers"], org["user_id"], issue_type="security_incident")
    created = client.post(
        f"{ISSUES_BASE}/{issue['id']}/breach-notification",
        headers=org["org_headers"],
        json={
            "breach_type": "personal_data",
            "personal_data_affected": True,
            "regulatory_notification_required": True,
            "regulatory_framework": "gdpr",
            "regulatory_notification_hours": 72,
            "supervisory_authority": "ICO",
            "subject_notification_required": True,
        },
    )
    assert created.status_code == 201
    breach_id = created.json()["id"]
    assert created.json()["special_category_data_involved"] is False
    assert "context_flags" in created.json()
    assert "regulator_notification_pending" in created.json()["context_flags"]

    updated = client.patch(
        f"{BREACH_BASE}/{breach_id}/privacy-fields",
        headers=org["org_headers"],
        json={
            "data_subjects_affected_count": 1500,
            "special_category_data_involved": True,
            "article34_required": True,
            "dpa_reference_number": "DPA-2026-009",
        },
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["data_subjects_affected_count"] == 1500
    assert body["special_category_data_involved"] is True
    assert body["article34_required"] is True
    assert body["dpa_reference_number"] == "DPA-2026-009"
    assert "article33_notice_text_missing" in body["context_flags"]

    # AI disabled fallback deterministic template.
    draft = client.post(
        f"{BREACH_BASE}/{breach_id}/generate-article33-draft",
        headers=org["org_headers"],
    )
    assert draft.status_code == 200
    draft_payload = draft.json()
    assert "GDPR Article 33 Notification Draft" in draft_payload["draft_text"]
    assert "To: ICO" in draft_payload["draft_text"]

    sent = client.post(
        f"{BREACH_BASE}/{breach_id}/record-article33-sent",
        headers=org["org_headers"],
        json={"sent_to": "ICO"},
    )
    assert sent.status_code == 200
    assert sent.json()["status"] == "regulator_notified"
    assert sent.json()["regulatory_notified_at"] is not None

    notified = client.post(
        f"{BREACH_BASE}/{breach_id}/record-subjects-notified",
        headers=org["org_headers"],
        json={"count": 1550},
    )
    assert notified.status_code == 200
    assert notified.json()["status"] == "subjects_notified"
    assert notified.json()["subjects_notified_at"] is not None
    assert notified.json()["regulatory_notified_at"] is not None
    assert notified.json()["data_subjects_affected_count"] == 1550

    # No auto-send side effects from draft generation.
    generated_at = datetime.now(UTC)
    _ = generated_at
    draft_outbox = (
        db_session.query(EmailOutbox)
        .filter(
            EmailOutbox.organization_id == uuid.UUID(org["organization_id"]),
            EmailOutbox.event_type == "breach.article33_draft",
        )
        .count()
    )
    assert draft_outbox == 0

    service_row = db_session.get(BreachNotification, uuid.UUID(breach_id))
    assert service_row is not None
    assert service_row.article33_notification_text is None

    # Deterministic draft helper still available for direct service usage with no transmission.
    fallback_payload = BreachNotificationService(db_session).generate_article33_draft(
        uuid.UUID(org["organization_id"]),
        uuid.UUID(breach_id),
        uuid.UUID(org["user_id"]),
        db_session,
    )
    assert "GDPR Article 33 Notification Draft" in fallback_payload["draft_text"]


def test_d89_breach_close_requires_article34_subject_notification_completion(client):
    org = bootstrap_org_user(client, email_prefix="d89-close-article34")
    issue = _create_issue(client, org["org_headers"], org["user_id"], issue_type="security_incident")

    created = client.post(
        f"{ISSUES_BASE}/{issue['id']}/breach-notification",
        headers=org["org_headers"],
        json={
            "breach_type": "personal_data",
            "personal_data_affected": True,
            "regulatory_notification_required": True,
            "regulatory_framework": "gdpr",
            "regulatory_notification_hours": 72,
            "supervisory_authority": "ICO",
            "subject_notification_required": True,
        },
    )
    assert created.status_code == 201
    breach_id = created.json()["id"]

    blocked = client.post(f"{BREACH_BASE}/{breach_id}/close", headers=org["org_headers"])
    assert blocked.status_code == 422
    assert "Article 34 subject notification" in blocked.json()["detail"]

    notified = client.post(
        f"{BREACH_BASE}/{breach_id}/record-subjects-notified",
        headers=org["org_headers"],
        json={"count": 12},
    )
    assert notified.status_code == 200
    assert notified.json()["subjects_notified_at"] is not None

    closed = client.post(f"{BREACH_BASE}/{breach_id}/close", headers=org["org_headers"])
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"


def test_d89_breach_flags_missing_supervisory_authority_when_regulator_notification_needed(client):
    org = bootstrap_org_user(client, email_prefix="d89-authority")
    issue = _create_issue(client, org["org_headers"], org["user_id"], issue_type="security_incident")

    created = client.post(
        f"{ISSUES_BASE}/{issue['id']}/breach-notification",
        headers=org["org_headers"],
        json={
            "breach_type": "personal_data",
            "personal_data_affected": True,
            "regulatory_notification_required": True,
            "regulatory_framework": "gdpr",
            "regulatory_notification_hours": 72,
            "subject_notification_required": False,
        },
    )
    assert created.status_code == 201
    assert "supervisory_authority_missing" in created.json()["context_flags"]


def test_d89_breach_list_rejects_invalid_status_filter(client):
    org = bootstrap_org_user(client, email_prefix="d89-list-status")
    listed = client.get(f"{BREACH_BASE}?status=not_a_real_status", headers=org["org_headers"])
    assert listed.status_code == 422
