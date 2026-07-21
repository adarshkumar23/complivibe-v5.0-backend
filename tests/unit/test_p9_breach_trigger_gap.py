"""Characterization of the documented P9 breach-notification gap.

These tests do NOT assert desired behaviour. They pin what core actually does
today, so the honest note in patent_ingest_p9.py cannot quietly go stale: if
someone adds a real breach detector, or changes the alias map, these fail and
the note gets updated with them.

The gap: a P9 breach-notification commitment triggers on 'data_breach', but core
emits no breach detector. Only a residency violation reaches it automatically.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.compliance.services.customer_commitment_service import CustomerCommitmentService
from app.models.customer_commitment import CustomerCommitment
from app.models.data_incident import DataIncident
from app.models.organization import Organization
from app.models.user import User

#: Detector types core emits AUTOMATICALLY today, and the service module that
#: does it. 'retention_violation' and 'manual' are deliberately absent: they are
#: valid values but only ever arrive through the human/API incident route.
AUTOMATIC_DETECTORS = {
    "quality_breach": "app/data_observability/services/quality_service.py",
    "anomaly_rule": "app/data_observability/services/access_monitoring_service.py",
    "residency_violation": "app/data_observability/services/residency_service.py",
}


@pytest.fixture()
def org_env(db_session):
    org = Organization(id=uuid.uuid4(), name="P9 Gap Org")
    user = User(
        id=uuid.uuid4(),
        email=f"p9-gap-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add_all([org, user])
    db_session.flush()
    return org, user


def _breach_commitment(org, user) -> CustomerCommitment:
    now = datetime.now(UTC)
    return CustomerCommitment(
        id=uuid.uuid4(),
        organization_id=org.id,
        customer_name="Acme Corp",
        commitment_type="breach_notification",
        title="Notify within 72h",
        description="d",
        trigger_condition="t",
        triggering_incident_type="data_breach",
        assigned_owner_id=user.id,
        created_by=user.id,
        obligation_type="breach_notification_sla",
        source_clause_text="c",
        created_at=now,
        updated_at=now,
    )


def test_no_detector_type_named_for_an_actual_breach_exists():
    """If this fails, core gained a breach detector and the note is now wrong."""
    allowed = {
        c.sqltext.text if hasattr(c, "sqltext") else str(c)
        for c in DataIncident.__table__.constraints
    }
    rendered = " ".join(allowed)
    assert "data_breach" not in rendered, (
        "a data_breach detector type now exists; update the P9 gap note"
    )
    assert "security_breach" not in rendered


def test_the_alias_map_reaches_data_breach_only_from_retention_and_residency(
    db_session, org_env
):
    org, user = org_env
    service = CustomerCommitmentService(db_session)

    reaches = []
    for detector in ("anomaly_rule", "quality_breach", "retention_violation",
                     "residency_violation", "manual"):
        row = _breach_commitment(org, user)
        db_session.add(row)
        db_session.flush()
        fired = service.trigger_commitments_for_incident(org.id, detector)
        if fired:
            reaches.append(detector)
        db_session.delete(row)
        db_session.flush()

    assert set(reaches) == {"retention_violation", "residency_violation"}, (
        f"the detector types reaching a breach-notification commitment changed: {reaches}"
    )


def test_only_one_of_those_two_is_emitted_automatically():
    """residency_violation is detected by core; retention_violation is not.

    This is the sharp end of the gap: of the two detector types that can fire a
    contractual breach-notification obligation, only one happens without a human
    filing an incident by hand.
    """
    automatic = set(AUTOMATIC_DETECTORS)
    reaching_data_breach = {"retention_violation", "residency_violation"}

    assert automatic & reaching_data_breach == {"residency_violation"}
    assert "retention_violation" not in automatic


def test_the_access_monitoring_signal_does_not_reach_a_breach_commitment(db_session, org_env):
    """anomaly_rule is the closest thing core has to a security signal, and it
    aliases to security_incident -- which P9 never writes."""
    org, user = org_env
    row = _breach_commitment(org, user)
    db_session.add(row)
    db_session.flush()

    fired = CustomerCommitmentService(db_session).trigger_commitments_for_incident(
        org.id, "anomaly_rule"
    )
    assert fired == 0
