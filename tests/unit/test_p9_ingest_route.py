"""The P9 contract-extraction ingest route, end to end.

Covers the four things that were wrong or missing in the upstream patch --
production-dead auth, org taken from the caller, a 500 on duplicate rows, and
no rate limit -- plus the path P9 was actually built for: an extracted
obligation becomes a live commitment that a real core incident triggers.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.ai_governance.services.governance_graph.scoped_key_service import PatentScopedKeyService
from app.compliance.services.customer_commitment_service import CustomerCommitmentService
from app.models.audit_log import AuditLog
from app.models.customer_commitment import CustomerCommitment
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.role import Role
from app.models.user import User

P9_PUSH = "/api/v1/patent-ingest/p9/commitments"


@pytest.fixture()
def org_env(db_session):
    org = Organization(id=uuid.uuid4(), name="P9 Route Org")
    other_org = Organization(id=uuid.uuid4(), name="P9 Other Org")
    role = Role(id=uuid.uuid4(), organization_id=org.id, name="owner", description="owner")
    owner = User(
        id=uuid.uuid4(),
        email=f"p9-owner-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add_all([org, other_org, role, owner])
    db_session.flush()
    db_session.add(
        Membership(
            id=uuid.uuid4(),
            organization_id=org.id,
            user_id=owner.id,
            role_id=role.id,
            status="active",
        )
    )
    db_session.flush()
    return {"org": org, "other_org": other_org, "owner": owner}


def _key(db_session, org_id, key_type="p9_ingest") -> str:
    return PatentScopedKeyService(db_session).provision_key(org_id, key_type, None)


def _body(owner_id, **overrides):
    body = {
        "customer_name": "Acme Corp",
        "commitment_type": "breach_notification",
        "title": "Notify Acme within 72 hours of a breach",
        "description": "Clause 14.2 breach-notification obligation.",
        "trigger_condition": "A data breach affecting Acme customer data",
        "triggering_incident_type": "data_breach",
        "sla_hours": 72,
        "linked_contract_ref": "acme-msa-2026",
        "assigned_owner_id": str(owner_id),
        "obligation_type": "breach_notification_sla",
        "extracted_params": {"deadline_hours": 72, "recipient": "customer"},
        "confidence_score": 0.93,
        "requires_human_review": False,
        "source_clause_text": "Supplier shall notify Customer within 72 hours.",
    }
    body.update(overrides)
    return body


# ------------------------------------------------------------------ auth


def test_push_without_a_key_is_rejected(client, db_session, org_env):
    assert client.post(P9_PUSH, json=_body(org_env["owner"].id)).status_code == 401


def test_push_with_an_unknown_key_is_rejected(client, db_session, org_env):
    resp = client.post(
        P9_PUSH,
        json=_body(org_env["owner"].id),
        headers={"Authorization": "Bearer not-a-real-key"},
    )
    assert resp.status_code == 403


@pytest.mark.parametrize("foreign_scope", ["p4_ingest", "ingest", "export"])
def test_another_satellites_key_cannot_authenticate_the_p9_route(
    client, db_session, org_env, foreign_scope
):
    """The required proof: cross-satellite key reuse must fail at the route."""
    foreign_key = _key(db_session, org_env["org"].id, foreign_scope)
    db_session.commit()

    resp = client.post(
        P9_PUSH,
        json=_body(org_env["owner"].id),
        headers={"Authorization": f"Bearer {foreign_key}"},
    )
    assert resp.status_code == 403, f"a '{foreign_scope}' key authenticated the P9 route"


def test_org_is_derived_from_the_key_not_from_the_caller(client, db_session, org_env):
    """A caller-supplied org must never redirect the write."""
    key = _key(db_session, org_env["org"].id)
    db_session.commit()

    resp = client.post(
        P9_PUSH,
        json=_body(org_env["owner"].id, organization_id=str(org_env["other_org"].id)),
        headers={
            "Authorization": f"Bearer {key}",
            "X-Organization-Id": str(org_env["other_org"].id),
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["organization_id"] == str(org_env["org"].id)

    leaked = db_session.execute(
        select(CustomerCommitment).where(
            CustomerCommitment.organization_id == org_env["other_org"].id
        )
    ).scalars().all()
    assert leaked == [], "the write landed in the org named by the caller"


# ------------------------------------------------- the five P9 fields persist


def test_all_five_p9_fields_persist_and_return_over_http(client, db_session, org_env):
    key = _key(db_session, org_env["org"].id)
    db_session.commit()

    resp = client.post(
        P9_PUSH, json=_body(org_env["owner"].id), headers={"Authorization": f"Bearer {key}"}
    )
    assert resp.status_code == 201, resp.text
    payload = resp.json()

    assert payload["obligation_type"] == "breach_notification_sla"
    assert payload["extracted_params"] == {"deadline_hours": 72, "recipient": "customer"}
    assert float(payload["confidence_score"]) == pytest.approx(0.93)
    assert payload["requires_human_review"] is False
    assert payload["source_clause_text"] == "Supplier shall notify Customer within 72 hours."

    stored = db_session.execute(
        select(CustomerCommitment).where(CustomerCommitment.id == uuid.UUID(payload["id"]))
    ).scalar_one()
    assert stored.obligation_type == "breach_notification_sla"
    assert stored.extracted_params == {"deadline_hours": 72, "recipient": "customer"}
    assert float(stored.confidence_score) == pytest.approx(0.93)
    assert stored.source_clause_text == "Supplier shall notify Customer within 72 hours."


def test_the_commitment_is_attributed_to_the_system_account(client, db_session, org_env):
    """There is no human on a scoped-key push, so created_by must be the
    automation account rather than a borrowed real user."""
    key = _key(db_session, org_env["org"].id)
    db_session.commit()

    resp = client.post(
        P9_PUSH, json=_body(org_env["owner"].id), headers={"Authorization": f"Bearer {key}"}
    )
    assert resp.status_code == 201, resp.text

    stored = db_session.execute(
        select(CustomerCommitment).where(CustomerCommitment.id == uuid.UUID(resp.json()["id"]))
    ).scalar_one()
    creator = db_session.execute(select(User).where(User.id == stored.created_by)).scalar_one()
    assert creator.is_system_account is True
    assert stored.assigned_owner_id == org_env["owner"].id


def test_a_p9_specific_audit_entry_records_the_extraction(client, db_session, org_env):
    key = _key(db_session, org_env["org"].id)
    db_session.commit()

    resp = client.post(
        P9_PUSH, json=_body(org_env["owner"].id), headers={"Authorization": f"Bearer {key}"}
    )
    assert resp.status_code == 201

    entries = db_session.execute(
        select(AuditLog).where(AuditLog.action == "customer_commitment.p9_auto_registered")
    ).scalars().all()
    assert len(entries) == 1
    assert entries[0].metadata_json["source"] == "p9_contract_extraction_pipeline"


# --------------------------------------------------- core does not trust the satellite


def test_core_rejects_an_obligation_flagged_for_human_review(client, db_session, org_env):
    """The satellite gates on confidence; core does not take its word for it."""
    key = _key(db_session, org_env["org"].id)
    db_session.commit()

    resp = client.post(
        P9_PUSH,
        json=_body(org_env["owner"].id, requires_human_review=True),
        headers={"Authorization": f"Bearer {key}"},
    )
    assert resp.status_code == 422, resp.text
    assert "human review" in resp.text.lower()

    assert db_session.execute(select(CustomerCommitment)).scalars().all() == []


def test_an_unknown_obligation_type_is_refused(client, db_session, org_env):
    key = _key(db_session, org_env["org"].id)
    db_session.commit()

    resp = client.post(
        P9_PUSH,
        json=_body(org_env["owner"].id, obligation_type="something_invented"),
        headers={"Authorization": f"Bearer {key}"},
    )
    assert resp.status_code == 422


def test_an_owner_outside_the_key_org_is_refused(client, db_session, org_env):
    """assigned_owner_id is still validated against core's membership rules."""
    key = _key(db_session, org_env["org"].id)
    stranger = User(
        id=uuid.uuid4(),
        email=f"stranger-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(stranger)
    db_session.commit()

    resp = client.post(
        P9_PUSH,
        json=_body(stranger.id),
        headers={"Authorization": f"Bearer {key}"},
    )
    assert resp.status_code == 422


# ------------------------------------------------------------- duplicate handling


def test_a_retried_upload_is_idempotent_rather_than_duplicated(client, db_session, org_env):
    key = _key(db_session, org_env["org"].id)
    db_session.commit()
    headers = {"Authorization": f"Bearer {key}", "X-P9-Upload-Id": "upload-1"}

    first = client.post(P9_PUSH, json=_body(org_env["owner"].id), headers=headers)
    second = client.post(P9_PUSH, json=_body(org_env["owner"].id), headers=headers)

    assert first.status_code == 201, first.text
    assert second.status_code == 200, second.text
    assert first.json()["id"] == second.json()["id"]

    rows = db_session.execute(select(CustomerCommitment)).scalars().all()
    assert len(rows) == 1


def test_ambiguous_duplicates_return_a_clear_conflict_not_a_500(client, db_session, org_env):
    """Two pre-existing rows for the same clause used to raise
    MultipleResultsFound inside scalar_one_or_none and surface as a 500."""
    key = _key(db_session, org_env["org"].id)
    now = datetime.now(UTC)
    for _ in range(2):
        db_session.add(
            CustomerCommitment(
                id=uuid.uuid4(),
                organization_id=org_env["org"].id,
                customer_name="Acme Corp",
                commitment_type="breach_notification",
                title="Pre-existing duplicate",
                description="d",
                trigger_condition="t",
                assigned_owner_id=org_env["owner"].id,
                created_by=org_env["owner"].id,
                linked_contract_ref="acme-msa-2026",
                source_clause_text="Supplier shall notify Customer within 72 hours.",
                created_at=now,
                updated_at=now,
            )
        )
    db_session.commit()

    resp = client.post(
        P9_PUSH,
        json=_body(org_env["owner"].id),
        headers={"Authorization": f"Bearer {key}", "X-P9-Upload-Id": "upload-1"},
    )
    assert resp.status_code == 409, resp.text
    assert resp.status_code != 500
    assert "duplicate" in resp.text.lower() or "ambiguous" in resp.text.lower()


def test_the_route_carries_a_rate_limit():
    """P2 and P4 ingest both rate-limit; P9 shipped without one.

    slowapi's limit() decorator wraps the handler with functools.wraps, so
    __wrapped__ is the observable trace of it. That is a real discriminator
    rather than a truism: the twelve handlers in the equivalent human-facing
    router carry no limiter and none of them has __wrapped__, which this test
    asserts alongside so the check cannot silently start passing for free.
    """
    import app.api.v1.customer_commitments as unlimited_router
    from app.compliance.routers import patent_ingest_p9

    unlimited = [
        getattr(unlimited_router, name)
        for name in dir(unlimited_router)
        if callable(getattr(unlimited_router, name))
        and getattr(getattr(unlimited_router, name), "__module__", "") == unlimited_router.__name__
    ]
    assert unlimited, "expected handlers in the comparison router"
    assert not any(hasattr(f, "__wrapped__") for f in unlimited), (
        "__wrapped__ no longer discriminates rate-limited handlers"
    )

    assert hasattr(patent_ingest_p9.ingest_p9_commitment, "__wrapped__"), (
        "the P9 ingest handler is not wrapped by the rate limiter"
    )


# ==================================================================== END TO END


@pytest.mark.parametrize(
    "detector_type",
    [
        # The only detector core emits AUTOMATICALLY that reaches a
        # breach-notification commitment. This is the genuinely end-to-end path.
        "residency_violation",
        # Also reaches it, but only ever filed by hand -- nothing in core emits
        # it. See test_p9_breach_trigger_gap.py.
        "retention_violation",
    ],
)
def test_end_to_end_extracted_obligation_is_fired_by_a_real_core_incident(
    client, db_session, org_env, detector_type
):
    """The path that actually works today, in one test.

    satellite push -> authenticated by a p9_ingest key -> commitment persisted
    with all five P9 fields -> a real core incident type ->
    trigger_commitments_for_incident fires it.
    """
    key = _key(db_session, org_env["org"].id)
    db_session.commit()

    resp = client.post(
        P9_PUSH, json=_body(org_env["owner"].id), headers={"Authorization": f"Bearer {key}"}
    )
    assert resp.status_code == 201, resp.text
    commitment_id = uuid.UUID(resp.json()["id"])

    stored = db_session.execute(
        select(CustomerCommitment).where(CustomerCommitment.id == commitment_id)
    ).scalar_one()
    assert stored.status == "active"
    assert stored.obligation_type == "breach_notification_sla"
    assert stored.confidence_score is not None

    # Both are real DataIncident.detector_type values; core aliases each to
    # data_breach, which is what this commitment is configured to trigger on.
    fired = CustomerCommitmentService(db_session).trigger_commitments_for_incident(
        org_env["org"].id,
        detector_type,
        incident_id=uuid.uuid4(),
    )
    assert fired == 1, "the machine-extracted commitment was not triggered"

    db_session.expunge_all()
    after = db_session.execute(
        select(CustomerCommitment).where(CustomerCommitment.id == commitment_id)
    ).scalar_one()
    assert after.status == "triggered"
    assert after.triggered_at is not None
    # The P9 provenance survives the trigger.
    assert after.obligation_type == "breach_notification_sla"
    assert after.source_clause_text == "Supplier shall notify Customer within 72 hours."
