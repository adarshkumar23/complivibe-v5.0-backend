from __future__ import annotations

import uuid

from app.models.data_principal_nomination import DataPrincipalNomination
from app.privacy.services.consent_service import ConsentService
from app.privacy.services.nomination_service import NominationService
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_consent_cookie_notice_d85_d87_d88 import CONSENT_BASE, _create_processing_activity


def test_guardian_consent_requires_relationship_and_verification_method(client):
    org = bootstrap_org_user(client, email_prefix="dpdp-guardian")
    activity = _create_processing_activity(client, org["org_headers"], org["user_id"])

    rejected = client.post(
        CONSENT_BASE,
        headers=org["org_headers"],
        json={
            "processing_activity_id": activity["id"],
            "subject_identifier": "minor-subject-1",
            "consent_mechanism": "written_form",
            "granted": True,
            "is_minor_or_guardian_managed": True,
        },
    )
    assert rejected.status_code == 422

    accepted = client.post(
        CONSENT_BASE,
        headers=org["org_headers"],
        json={
            "processing_activity_id": activity["id"],
            "subject_identifier": "minor-subject-1",
            "consent_mechanism": "written_form",
            "granted": True,
            "is_minor_or_guardian_managed": True,
            "guardian_relationship": "parent",
            "guardian_verification_method": "digilocker",
            "guardian_identity_reference": "digilocker-ref-abc",
        },
    )
    assert accepted.status_code == 201
    body = accepted.json()
    assert body["is_minor_or_guardian_managed"] is True
    assert body["guardian_relationship"] == "parent"
    assert body["guardian_verification_method"] == "digilocker"
    assert body["guardian_verified_at"] is not None


def test_nomination_create_activate_revoke_lifecycle(db_session):
    org = uuid.uuid4()
    subject_hash = ConsentService.hash_subject_identifier("subject-nom-1")
    creator = uuid.uuid4()

    service = NominationService(db_session)
    nomination = service.create_nomination(
        org_id=org,
        subject_identifier="subject-nom-1",
        nominee_name="Jane Nominee",
        nominee_contact="jane@example.io",
        activation_trigger="incapacity",
        actor_user_id=creator,
    )
    assert nomination.status == "active"
    assert nomination.subject_identifier_hash == subject_hash

    # get_active_nomination finds the nomination currently in force (i.e. activated via
    # its death/incapacity trigger), not a merely-created, not-yet-triggered one.
    not_yet_activated = service.get_active_nomination(org, "subject-nom-1")
    assert not_yet_activated is None

    activated = service.activate_nomination(org, nomination.id, actor_user_id=creator)
    assert activated.status == "activated"
    assert activated.activated_at is not None

    row = db_session.get(DataPrincipalNomination, nomination.id)
    assert row.status == "activated"

    active = service.get_active_nomination(org, "subject-nom-1")
    assert active is not None
    assert active.id == nomination.id


def test_nomination_revoke(db_session):
    org = uuid.uuid4()
    service = NominationService(db_session)
    nomination = service.create_nomination(
        org_id=org,
        subject_identifier="subject-nom-2",
        nominee_name="John Nominee",
        nominee_contact=None,
        activation_trigger="death",
        actor_user_id=None,
    )

    revoked = service.revoke_nomination(org, nomination.id, reason="changed my mind", actor_user_id=None)
    assert revoked.status == "revoked"
    assert revoked.revocation_reason == "changed my mind"

    assert service.get_active_nomination(org, "subject-nom-2") is None
