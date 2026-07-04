from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from app.compliance.services.customer_commitment_service import CustomerCommitmentService
from app.compliance.services.subprocessor_service import SubprocessorService
from app.models.commitment_notification_log import CommitmentNotificationLog
from app.models.customer_commitment import CustomerCommitment
from app.models.email_outbox import EmailOutbox
from app.models.subprocessor import Subprocessor
from tests.helpers.auth_org import bootstrap_org_user

SUBPROCESSOR_BASE = "/api/v1/compliance/subprocessors"
COMMITMENT_BASE = "/api/v1/compliance/customer-commitments"


def _create_subprocessor(client, headers: dict[str, str], *, name: str) -> dict:
    response = client.post(
        SUBPROCESSOR_BASE,
        headers=headers,
        json={
            "name": name,
            "service_description": "Processes customer support data",
            "data_types_processed": ["email", "name"],
            "legal_basis": "contract",
            "geographic_locations": ["US"],
            "data_transfer_mechanism": "sccs",
            "controller_type": "processor",
            "risk_level": "medium",
            "status": "active",
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_commitment(
    client,
    headers: dict[str, str],
    *,
    title: str,
    commitment_type: str,
    assigned_owner_id: str,
    trigger_date: date | None = None,
    notification_days_before: int = 7,
    sla_hours: int | None = None,
) -> dict:
    response = client.post(
        COMMITMENT_BASE,
        headers=headers,
        json={
            "customer_name": "Acme Corp",
            "customer_email": "security@acme.example",
            "commitment_type": commitment_type,
            "title": title,
            "description": "Contractual commitment",
            "trigger_condition": "Contract milestone",
            "trigger_date": trigger_date.isoformat() if trigger_date else None,
            "notification_days_before": notification_days_before,
            "sla_hours": sla_hours,
            "linked_contract_ref": "MSA-123",
            "assigned_owner_id": assigned_owner_id,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_a54_subprocessor_lifecycle_sweep_dashboard_and_org_isolation(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="a54-org-a")
    org_b = bootstrap_org_user(client, email_prefix="a54-org-b")

    created = _create_subprocessor(client, org_a["org_headers"], name="Stripe")
    assert created["name"] == "Stripe"
    assert created["legal_basis"] == "contract"

    pending_to_signed = client.post(
        f"{SUBPROCESSOR_BASE}/{created['id']}/dpa-status",
        headers=org_a["org_headers"],
        json={
            "new_status": "signed",
            "signed_at": datetime.now(UTC).isoformat(),
            "expiry_date": (date.today() + timedelta(days=10)).isoformat(),
        },
    )
    assert pending_to_signed.status_code == 200
    assert pending_to_signed.json()["dpa_status"] == "signed"
    assert pending_to_signed.json()["dpa_signed_at"] is not None

    transfer = client.post(
        f"{SUBPROCESSOR_BASE}/{created['id']}/transfers",
        headers=org_a["org_headers"],
        json={
            "origin_country": "DE",
            "destination_country": "US",
            "data_categories": ["email"],
            "transfer_mechanism": "sccs",
            "legal_basis": "contract",
            "is_active": True,
        },
    )
    assert transfer.status_code == 201
    assert transfer.json()["subprocessor_id"] == created["id"]

    signed_to_expired = client.post(
        f"{SUBPROCESSOR_BASE}/{created['id']}/dpa-status",
        headers=org_a["org_headers"],
        json={"new_status": "expired"},
    )
    assert signed_to_expired.status_code == 200
    assert signed_to_expired.json()["dpa_status"] == "expired"

    invalid_transition = client.post(
        f"{SUBPROCESSOR_BASE}/{created['id']}/dpa-status",
        headers=org_a["org_headers"],
        json={"new_status": "pending"},
    )
    assert invalid_transition.status_code == 422

    expiring_soon = _create_subprocessor(client, org_a["org_headers"], name="Zendesk")
    client.post(
        f"{SUBPROCESSOR_BASE}/{expiring_soon['id']}/dpa-status",
        headers=org_a["org_headers"],
        json={"new_status": "signed", "expiry_date": (date.today() + timedelta(days=7)).isoformat()},
    )

    past_expiry = _create_subprocessor(client, org_a["org_headers"], name="Legacy Processor")
    client.post(
        f"{SUBPROCESSOR_BASE}/{past_expiry['id']}/dpa-status",
        headers=org_a["org_headers"],
        json={"new_status": "signed", "expiry_date": (date.today() - timedelta(days=1)).isoformat()},
    )

    pending = _create_subprocessor(client, org_a["org_headers"], name="No DPA Yet")
    assert pending["dpa_status"] == "pending"

    sweep_result = SubprocessorService(db_session).sweep_expired_dpas(uuid.UUID(org_a["organization_id"]))
    db_session.commit()
    assert sweep_result["expiring_soon"] >= 1
    assert sweep_result["expired"] >= 1
    assert sweep_result["reminders_queued"] >= 1

    refreshed_past = db_session.get(Subprocessor, uuid.UUID(past_expiry["id"]))
    assert refreshed_past is not None
    assert refreshed_past.dpa_status == "expired"

    dashboard_response = client.get(f"{SUBPROCESSOR_BASE}/gdpr-dashboard", headers=org_a["org_headers"])
    assert dashboard_response.status_code == 200
    dashboard = dashboard_response.json()
    assert dashboard["transfers_outside_eea"] >= 1
    assert dashboard["missing_dpa_count"] >= 2  # pending + expired

    soft_delete_blocked = client.delete(f"{SUBPROCESSOR_BASE}/{pending['id']}", headers=org_a["org_headers"])
    assert soft_delete_blocked.status_code == 422

    list_a = client.get(SUBPROCESSOR_BASE, headers=org_a["org_headers"])
    assert list_a.status_code == 200
    list_b = client.get(SUBPROCESSOR_BASE, headers=org_b["org_headers"])
    assert list_b.status_code == 200
    ids_a = {row["id"] for row in list_a.json()}
    ids_b = {row["id"] for row in list_b.json()}
    assert created["id"] in ids_a
    assert created["id"] not in ids_b


def test_a54_subprocessor_gdpr_completeness_validation(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a54-gdpr")

    incomplete = client.post(
        SUBPROCESSOR_BASE,
        headers=org["org_headers"],
        json={
            "name": "Incomplete Processor",
            "service_description": "Missing fields",
            "data_types_processed": [],
            "legal_basis": "contract",
            "geographic_locations": ["US"],
            "controller_type": "processor",
            "risk_level": "medium",
            "status": "active",
        },
    )
    assert incomplete.status_code == 422
    detail = incomplete.json()["detail"]
    assert "data_types_processed" in detail
    assert "data_transfer_mechanism" in detail

    missing_locations = client.post(
        SUBPROCESSOR_BASE,
        headers=org["org_headers"],
        json={
            "name": "No Location Processor",
            "service_description": "Missing location",
            "data_types_processed": ["email"],
            "legal_basis": "contract",
            "geographic_locations": [],
            "controller_type": "processor",
            "risk_level": "medium",
            "status": "active",
        },
    )
    assert missing_locations.status_code == 422
    assert "geographic_locations" in missing_locations.json()["detail"]

    complete = _create_subprocessor(client, org["org_headers"], name="Complete Processor")
    partial = client.patch(
        f"{SUBPROCESSOR_BASE}/{complete['id']}",
        headers=org["org_headers"],
        json={"contact_email": "privacy@example.com"},
    )
    assert partial.status_code == 200
    assert partial.json()["contact_email"] == "privacy@example.com"
    assert partial.json()["data_transfer_mechanism"] == "sccs"

    clearing_required_transfer = client.patch(
        f"{SUBPROCESSOR_BASE}/{complete['id']}",
        headers=org["org_headers"],
        json={"data_transfer_mechanism": None},
    )
    assert clearing_required_transfer.status_code == 422
    assert "data_transfer_mechanism" in clearing_required_transfer.json()["detail"]


def test_item2_gdpr_dashboard_counts_geographic_locations_without_double_counting(client):
    org = bootstrap_org_user(client, email_prefix="item2-gdpr")

    baseline = client.get(f"{SUBPROCESSOR_BASE}/gdpr-dashboard", headers=org["org_headers"])
    assert baseline.status_code == 200
    baseline_count = baseline.json()["transfers_outside_eea"]

    # Subprocessor with a non-EEA geographic_locations entry but NO explicit transfer record.
    location_only = _create_subprocessor(client, org["org_headers"], name="Location-Only Vendor")
    location_only_dashboard = client.get(f"{SUBPROCESSOR_BASE}/gdpr-dashboard", headers=org["org_headers"])
    assert location_only_dashboard.status_code == 200
    assert location_only_dashboard.json()["transfers_outside_eea"] == baseline_count + 1

    # Subprocessor with BOTH a non-EEA geographic_locations entry AND an explicit non-EEA transfer
    # record -- must count once, not twice.
    both_signals = _create_subprocessor(client, org["org_headers"], name="Both-Signals Vendor")
    transfer = client.post(
        f"{SUBPROCESSOR_BASE}/{both_signals['id']}/transfers",
        headers=org["org_headers"],
        json={
            "origin_country": "DE",
            "destination_country": "US",
            "data_categories": ["email"],
            "transfer_mechanism": "sccs",
            "legal_basis": "contract",
            "is_active": True,
        },
    )
    assert transfer.status_code == 201

    final_dashboard = client.get(f"{SUBPROCESSOR_BASE}/gdpr-dashboard", headers=org["org_headers"])
    assert final_dashboard.status_code == 200
    assert final_dashboard.json()["transfers_outside_eea"] == baseline_count + 2


def test_a55_commitment_types_workflow_sweeps_and_dashboard(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a55-commitments")
    owner_id = org["user_id"]

    commitment_types = [
        "breach_notification",
        "subprocessor_notice",
        "audit_right",
        "data_deletion",
        "data_portability",
        "sla",
        "security_assessment",
        "custom",
    ]
    created_ids: list[str] = []
    for idx, commitment_type in enumerate(commitment_types):
        item = _create_commitment(
            client,
            org["org_headers"],
            title=f"Type {idx}",
            commitment_type=commitment_type,
            assigned_owner_id=owner_id,
            trigger_date=date.today() + timedelta(days=20),
            sla_hours=72 if commitment_type == "breach_notification" else None,
        )
        created_ids.append(item["id"])

    active_fulfill_block = client.post(
        f"{COMMITMENT_BASE}/{created_ids[1]}/fulfill",
        headers=org["org_headers"],
        json={"notes": "too early"},
    )
    assert active_fulfill_block.status_code == 422

    triggered = client.post(f"{COMMITMENT_BASE}/{created_ids[0]}/trigger", headers=org["org_headers"])
    assert triggered.status_code == 200
    assert triggered.json()["status"] == "triggered"
    assert triggered.json()["triggered_at"] is not None

    notifications = client.get(f"{COMMITMENT_BASE}/{created_ids[0]}/notifications", headers=org["org_headers"])
    assert notifications.status_code == 200
    assert any(row["notification_type"] == "triggered" for row in notifications.json())

    fulfilled = client.post(
        f"{COMMITMENT_BASE}/{created_ids[0]}/fulfill",
        headers=org["org_headers"],
        json={"notes": "completed"},
    )
    assert fulfilled.status_code == 200
    assert fulfilled.json()["status"] == "fulfilled"

    to_waive = client.post(f"{COMMITMENT_BASE}/{created_ids[2]}/trigger", headers=org["org_headers"])
    assert to_waive.status_code == 200
    waived = client.post(
        f"{COMMITMENT_BASE}/{created_ids[2]}/waive",
        headers=org["org_headers"],
        json={"reason": "Customer waived this requirement"},
    )
    assert waived.status_code == 200
    assert waived.json()["status"] == "waived"
    assert waived.json()["waived_at"] is not None
    assert waived.json()["waiver_reason"] == "Customer waived this requirement"

    overdue_candidate = _create_commitment(
        client,
        org["org_headers"],
        title="Overdue Candidate",
        commitment_type="custom",
        assigned_owner_id=owner_id,
        trigger_date=date.today() - timedelta(days=5),
    )
    trigger_overdue = client.post(f"{COMMITMENT_BASE}/{overdue_candidate['id']}/trigger", headers=org["org_headers"])
    assert trigger_overdue.status_code == 200

    reminder_candidate = _create_commitment(
        client,
        org["org_headers"],
        title="Reminder Candidate",
        commitment_type="custom",
        assigned_owner_id=owner_id,
        trigger_date=date.today() + timedelta(days=2),
        notification_days_before=7,
    )

    service = CustomerCommitmentService(db_session)
    first_sweep = service.process_commitment_triggers()
    db_session.commit()
    second_sweep = service.process_commitment_triggers()
    db_session.commit()

    assert first_sweep["reminders"] >= 1
    assert first_sweep["overdue"] >= 1

    reminder_logs = db_session.query(CommitmentNotificationLog).filter(
        CommitmentNotificationLog.commitment_id == uuid.UUID(reminder_candidate["id"]),
        CommitmentNotificationLog.notification_type == "reminder",
    )
    assert reminder_logs.count() == 1
    assert second_sweep["reminders"] <= first_sweep["reminders"]

    overdue_row = db_session.get(CustomerCommitment, uuid.UUID(overdue_candidate["id"]))
    assert overdue_row is not None
    assert overdue_row.status == "overdue"

    breach_ok = _create_commitment(
        client,
        org["org_headers"],
        title="Breach SLA OK",
        commitment_type="breach_notification",
        assigned_owner_id=owner_id,
        trigger_date=date.today(),
        sla_hours=72,
    )
    breach_bad = _create_commitment(
        client,
        org["org_headers"],
        title="Breach SLA Miss",
        commitment_type="breach_notification",
        assigned_owner_id=owner_id,
        trigger_date=date.today(),
        sla_hours=72,
    )

    now = datetime.now(UTC)
    ok_row = db_session.get(CustomerCommitment, uuid.UUID(breach_ok["id"]))
    bad_row = db_session.get(CustomerCommitment, uuid.UUID(breach_bad["id"]))
    assert ok_row is not None and bad_row is not None

    ok_row.status = "fulfilled"
    ok_row.triggered_at = now - timedelta(hours=10)
    ok_row.fulfilled_at = now

    bad_row.status = "fulfilled"
    bad_row.triggered_at = now - timedelta(hours=100)
    bad_row.fulfilled_at = now
    db_session.commit()

    dashboard_response = client.get(f"{COMMITMENT_BASE}/dashboard", headers=org["org_headers"])
    assert dashboard_response.status_code == 200
    dashboard = dashboard_response.json()
    assert dashboard["due_within_30_days"] >= 1
    assert dashboard["breach_notification_sla_compliance"]["total_breach_commitments"] >= 2
    assert dashboard["breach_notification_sla_compliance"]["fulfilled_within_sla"] >= 1
    assert dashboard["breach_notification_sla_compliance"]["breached_sla"] >= 1

    triggered_delete_block = client.delete(f"{COMMITMENT_BASE}/{overdue_candidate['id']}", headers=org["org_headers"])
    assert triggered_delete_block.status_code == 422

    deletable = _create_commitment(
        client,
        org["org_headers"],
        title="Deletable Active",
        commitment_type="custom",
        assigned_owner_id=owner_id,
        trigger_date=date.today() + timedelta(days=14),
    )
    deleted = client.delete(f"{COMMITMENT_BASE}/{deletable['id']}", headers=org["org_headers"])
    assert deleted.status_code == 200
    assert deleted.json()["deleted_at"] is not None

    outbox_count = db_session.query(EmailOutbox).filter(EmailOutbox.organization_id == uuid.UUID(org["organization_id"])).count()
    assert outbox_count >= 1
