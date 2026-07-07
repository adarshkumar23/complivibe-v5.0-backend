from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.models.data_subject_request import DataSubjectRequest
from app.models.dsr_sla_tracking import DSRSLATracking
from app.privacy.services.dsar_service import DSARService
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/privacy/dsr"


def _create_internal_request(client, headers: dict[str, str], **overrides):
    payload = {
        "request_type": "access",
        "subject_name": "Jane Doe",
        "subject_email": "jane@example.com",
        "description": "Please provide my data",
        "regulatory_framework": "gdpr",
    }
    payload.update(overrides)
    response = client.post(BASE, headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def test_d84_d90_request_lifecycle_and_sla(client, db_session):
    org = bootstrap_org_user(client, email_prefix="d84-org")
    year = datetime.now(UTC).year

    first = _create_internal_request(client, org["org_headers"], subject_email="one@example.com")
    assert first["request_ref"] == f"DSR-{year}-001"
    assert "age_days" in first
    assert "context_flags" in first
    assert first["is_overdue"] is False

    second = _create_internal_request(client, org["org_headers"], subject_email="two@example.com")
    assert second["request_ref"] == f"DSR-{year}-002"
    assert "unassigned_request" in second["context_flags"]

    first_deadline = datetime.fromisoformat(first["response_deadline"])
    assert 29 <= (first_deadline - datetime.fromisoformat(first["received_at"])).days <= 31

    ccpa = _create_internal_request(
        client,
        org["org_headers"],
        subject_email="ccpa@example.com",
        regulatory_framework="ccpa",
    )
    assert ccpa["deadline_days"] == 45
    ccpa_deadline = datetime.fromisoformat(ccpa["response_deadline"])
    assert 44 <= (ccpa_deadline - datetime.fromisoformat(ccpa["received_at"])).days <= 46

    # Public endpoint, no JWT.
    public_submit = client.post(
        f"{BASE}/submit",
        json={
            "organization_id": org["organization_id"],
            "request_type": "erasure",
            "subject_name": "Public User",
            "subject_email": "public@example.com",
            "description": "Delete my records",
            "regulatory_framework": "gdpr",
        },
    )
    assert public_submit.status_code == 201
    assert public_submit.json()["message"] == "Request received."

    transition_ok = client.post(
        f"{BASE}/{first['id']}/transition",
        headers=org["org_headers"],
        json={"new_status": "in_progress", "notes": "Started"},
    )
    assert transition_ok.status_code == 200
    assert transition_ok.json()["status"] == "in_progress"

    transition_bad = client.post(
        f"{BASE}/{first['id']}/transition",
        headers=org["org_headers"],
        json={"new_status": "received"},
    )
    assert transition_bad.status_code == 422

    done = client.post(
        f"{BASE}/{first['id']}/transition",
        headers=org["org_headers"],
        json={"new_status": "fulfilled"},
    )
    assert done.status_code == 200
    assert done.json()["fulfilled_at"] is not None

    terminal = client.post(
        f"{BASE}/{first['id']}/transition",
        headers=org["org_headers"],
        json={"new_status": "in_progress"},
    )
    assert terminal.status_code == 422

    grant = client.post(
        f"{BASE}/{second['id']}/grant-extension",
        headers=org["org_headers"],
        json={"reason": "Complex request"},
    )
    assert grant.status_code == 200
    assert grant.json()["extension_granted"] is True
    assert grant.json()["extension_deadline"] is not None

    sla_row = (
        db_session.query(DSRSLATracking)
        .filter(DSRSLATracking.request_id == uuid.UUID(second["id"]))
        .first()
    )
    assert sla_row is not None
    assert sla_row.effective_deadline is not None

    verify = client.post(
        f"{BASE}/{second['id']}/verify-identity",
        headers=org["org_headers"],
    )
    assert verify.status_code == 200
    assert verify.json()["identity_verified"] is True
    assert verify.json()["status"] == "in_progress"
    assert "verified_pending_fulfillment" in verify.json()["context_flags"]

    step = client.post(
        f"{BASE}/{second['id']}/steps",
        headers=org["org_headers"],
        json={
            "step_type": "locate_data",
            "description": "Locate all records",
        },
    )
    assert step.status_code == 201
    assert step.json()["order_index"] == 1

    second_after_step = client.get(f"{BASE}/{second['id']}", headers=org["org_headers"])
    assert second_after_step.status_code == 200
    assert second_after_step.json()["step_completion_rate"] == 0.0

    step_complete = client.post(
        f"{BASE}/{second['id']}/steps/{step.json()['id']}/complete",
        headers=org["org_headers"],
        params={"notes": "Done"},
    )
    assert step_complete.status_code == 200
    assert step_complete.json()["completed_at"] is not None

    second_after_complete = client.get(f"{BASE}/{second['id']}", headers=org["org_headers"])
    assert second_after_complete.status_code == 200
    assert second_after_complete.json()["step_completion_rate"] == 100.0

    # Force SLA-breach condition and verify idempotent sweep.
    dsr_row = db_session.query(DataSubjectRequest).filter(DataSubjectRequest.id == uuid.UUID(second["id"])).first()
    assert dsr_row is not None
    dsr_row.response_deadline = datetime.now(UTC) - timedelta(days=2)
    dsr_row.extension_granted = False
    dsr_row.extension_deadline = None
    dsr_row.status = "in_progress"

    sla_row = db_session.query(DSRSLATracking).filter(DSRSLATracking.request_id == uuid.UUID(second["id"])).first()
    assert sla_row is not None
    sla_row.effective_deadline = datetime.now(UTC) - timedelta(days=1)
    sla_row.response_breached = False
    db_session.commit()

    sweep1 = DSARService(db_session).run_sla_sweep()
    assert sweep1["breaches_marked"] >= 1

    refreshed_sla = db_session.query(DSRSLATracking).filter(DSRSLATracking.request_id == uuid.UUID(second["id"])).first()
    assert refreshed_sla is not None
    assert refreshed_sla.response_breached is True

    sweep2 = DSARService(db_session).run_sla_sweep()
    assert sweep2["breaches_marked"] == 0

    summary = client.get(f"{BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    assert summary.json()["overdue_count"] >= 0
    assert "sla_compliance_rate" in summary.json()
    assert "open_count" in summary.json()
    assert "breached_open_count" in summary.json()
    assert "verified_pending_fulfillment_count" in summary.json()
    assert isinstance(summary.json()["context_flags"], list)

    listed = client.get(BASE, headers=org["org_headers"])
    assert listed.status_code == 200
    assert len(listed.json()) >= 2
    assert "days_to_deadline" in listed.json()[0]
    assert "step_completion_rate" in listed.json()[0]


def test_d84_d90_org_isolation(client):
    org_a = bootstrap_org_user(client, email_prefix="d84-org-a")
    org_b = bootstrap_org_user(client, email_prefix="d84-org-b")

    created = _create_internal_request(client, org_a["org_headers"], subject_email="iso@example.com")

    forbidden = client.get(f"{BASE}/{created['id']}", headers=org_b["org_headers"])
    assert forbidden.status_code == 404

    overdue_b = client.get(f"{BASE}/overdue", headers=org_b["org_headers"])
    assert overdue_b.status_code == 200
    assert overdue_b.json() == []
