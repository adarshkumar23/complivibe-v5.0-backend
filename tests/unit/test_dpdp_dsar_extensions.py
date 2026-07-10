from __future__ import annotations

import uuid

from app.privacy.services import dsar_service as dsar_service_module
from app.privacy.services.dsar_service import DSARService
from app.privacy.services.nomination_service import NominationService
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/privacy/dsr"


def test_grievance_request_gets_ninety_day_deadline(client):
    org = bootstrap_org_user(client, email_prefix="dpdp-grievance")
    response = client.post(
        BASE,
        headers=org["org_headers"],
        json={
            "request_type": "access",
            "subject_name": "Jane Principal",
            "subject_email": "jane@example.io",
            "regulatory_framework": "dpdp",
            "request_subtype": "grievance",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["deadline_days"] == 90
    assert body["request_subtype"] == "grievance"


def test_rights_request_keeps_default_thirty_day_deadline(client):
    org = bootstrap_org_user(client, email_prefix="dpdp-rights")
    response = client.post(
        BASE,
        headers=org["org_headers"],
        json={
            "request_type": "access",
            "subject_name": "Jane Principal",
            "subject_email": "jane@example.io",
            "regulatory_framework": "dpdp",
        },
    )
    assert response.status_code == 201
    assert response.json()["deadline_days"] == 30


def test_erasure_blocked_by_retention_conflict_and_overridable(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="dpdp-erasure")

    fake_conflict = {
        "conflicts": [
            {
                "blocked": True,
                "reason": "RBI KYC Master Direction requires retention until account closure + 5 years",
                "data_category": "kyc_identity_documents",
            }
        ]
    }
    monkeypatch.setattr(
        dsar_service_module, "check_retention_conflict", lambda db, org_id, cats, relationship_end_date=None: fake_conflict
    )

    create = client.post(
        BASE,
        headers=org["org_headers"],
        json={
            "request_type": "erasure",
            "subject_name": "Jane Principal",
            "subject_email": "jane@example.io",
            "regulatory_framework": "dpdp",
            "data_categories": ["kyc_identity_documents"],
        },
    )
    assert create.status_code == 201
    request_id = create.json()["id"]

    verify = client.post(f"{BASE}/{request_id}/verify-identity", headers=org["org_headers"])
    assert verify.status_code == 200

    blocked = client.post(
        f"{BASE}/{request_id}/transition",
        headers=org["org_headers"],
        json={"new_status": "fulfilled"},
    )
    assert blocked.status_code == 409
    assert "conflict" in blocked.json()["detail"]

    still_open = client.get(f"{BASE}/{request_id}", headers=org["org_headers"])
    assert still_open.json()["context_flags"].count("retention_conflict_present") == 1

    no_reason = client.post(
        f"{BASE}/{request_id}/transition",
        headers=org["org_headers"],
        json={"new_status": "fulfilled", "override_retention_conflict": True},
    )
    assert no_reason.status_code == 422

    overridden = client.post(
        f"{BASE}/{request_id}/transition",
        headers=org["org_headers"],
        json={
            "new_status": "fulfilled",
            "override_retention_conflict": True,
            "override_reason": "Legal confirmed retention floor already elapsed for this customer",
        },
    )
    assert overridden.status_code == 200
    body = overridden.json()
    assert body["status"] == "fulfilled"
    assert body["retention_conflict_override_reason"] is not None
    assert "retention_conflict_present" not in body["context_flags"]


def test_nomination_aware_submission_requires_activated_nomination(client, db_session):
    org = bootstrap_org_user(client, email_prefix="dpdp-nominee-dsr")
    org_id = uuid.UUID(org["organization_id"])

    nomination_service = NominationService(db_session)
    nomination = nomination_service.create_nomination(
        org_id=org_id,
        subject_identifier="deceased-subject-1",
        nominee_name="Nominee Person",
        nominee_contact="nominee@example.io",
        activation_trigger="death",
        actor_user_id=None,
    )
    db_session.commit()

    rejected = client.post(
        BASE,
        headers=org["org_headers"],
        json={
            "request_type": "access",
            "subject_name": "Deceased Subject",
            "subject_email": "deceased@example.io",
            "subject_identifier": "deceased-subject-1",
            "regulatory_framework": "dpdp",
            "submitted_by_nominee_id": str(nomination.id),
        },
    )
    assert rejected.status_code == 422

    nomination_service.activate_nomination(org_id, nomination.id, actor_user_id=None)
    db_session.commit()

    accepted = client.post(
        BASE,
        headers=org["org_headers"],
        json={
            "request_type": "access",
            "subject_name": "Deceased Subject",
            "subject_email": "deceased@example.io",
            "subject_identifier": "deceased-subject-1",
            "regulatory_framework": "dpdp",
            "submitted_by_nominee_id": str(nomination.id),
        },
    )
    assert accepted.status_code == 201
    assert accepted.json()["submitted_by_nominee_id"] == str(nomination.id)
