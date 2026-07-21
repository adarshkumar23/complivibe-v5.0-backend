"""Audit trail for patent scoped-key provisioning/rotation (2026-07-21).

Closes the other half of the WS7-HIGH finding. SubsystemIngestKeyService.provision_key
was audited by a1a9e9f, but PatentScopedKeyService.provision_key -- a near-copy minting
the same class of credential for the P2/P3/P4/P9 satellites -- was left unaudited, so
p4_ingest/p9_ingest keys could be minted and rotated with no record of who did it.

There is no provisioning ROUTER for these keys today (app code only ever calls
resolve_org_by_key), so these tests drive the service directly. That is also why the
audit write belongs in the service: whenever a provisioning endpoint does get added,
it inherits the trail instead of having to remember to write one.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select

from app.ai_governance.services.governance_graph.scoped_key_service import PatentScopedKeyService
from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.models.patent_scoped_key import PatentScopedKey


@pytest.fixture()
def org(db_session):
    row = Organization(id=uuid.uuid4(), name="Patent Scoped Key Audit Org")
    db_session.add(row)
    db_session.flush()
    return row


def _audit_rows(db_session, org_id: uuid.UUID) -> list[AuditLog]:
    return list(
        db_session.execute(
            select(AuditLog)
            .where(
                AuditLog.organization_id == org_id,
                AuditLog.entity_type == "patent_scoped_keys",
            )
            .order_by(AuditLog.created_at.asc())
        )
        .scalars()
        .all()
    )


def _serialized(row: AuditLog) -> str:
    return json.dumps(
        {"m": row.metadata_json, "b": row.before_json, "a": row.after_json}, default=str
    )


def test_provisioning_a_patent_scoped_key_is_audited(db_session, org):
    actor = uuid.uuid4()
    raw_key = PatentScopedKeyService(db_session).provision_key(org.id, "p9_ingest", actor)

    db_session.expire_all()
    rows = _audit_rows(db_session, org.id)
    assert len(rows) == 1, "minting a satellite ingest key must leave an audit trail"
    row = rows[0]
    assert row.action == "patent_scoped_key.provisioned"
    assert row.organization_id == org.id
    assert row.actor_user_id == actor
    assert row.metadata_json["key_type"] == "p9_ingest"
    assert row.created_at is not None

    # entity_id must point at the real row, so the trail is joinable to the credential.
    key_row = db_session.execute(
        select(PatentScopedKey).where(
            PatentScopedKey.organization_id == org.id,
            PatentScopedKey.key_type == "p9_ingest",
        )
    ).scalar_one()
    assert row.entity_id == key_row.id


def test_rotating_a_patent_scoped_key_is_audited_as_a_rotation(db_session, org):
    actor = uuid.uuid4()
    service = PatentScopedKeyService(db_session)
    first = service.provision_key(org.id, "p4_ingest", actor)
    second = service.provision_key(org.id, "p4_ingest", actor)
    assert second != first

    db_session.expire_all()
    rows = _audit_rows(db_session, org.id)
    assert len(rows) == 2, "rotation must be audited separately from initial provisioning"
    assert [r.action for r in rows] == [
        "patent_scoped_key.provisioned",
        "patent_scoped_key.rotated",
    ]
    rotation = rows[1]
    assert rotation.metadata_json["key_type"] == "p4_ingest"
    assert rotation.actor_user_id == actor
    # The active-state transition is what makes a rotation reconstructable.
    assert rotation.before_json == {"is_active": True}
    assert rotation.after_json == {"is_active": True}


def test_key_types_are_audited_independently(db_session, org):
    service = PatentScopedKeyService(db_session)
    for key_type in ("p4_ingest", "p9_ingest"):
        service.provision_key(org.id, key_type, None)

    db_session.expire_all()
    rows = _audit_rows(db_session, org.id)
    assert [r.action for r in rows] == [
        "patent_scoped_key.provisioned",
        "patent_scoped_key.provisioned",
    ], "a second key TYPE is a new key, not a rotation of the first"
    assert sorted(r.metadata_json["key_type"] for r in rows) == ["p4_ingest", "p9_ingest"]


@pytest.mark.parametrize("key_type", ["export", "ingest", "p4_ingest", "p9_ingest"])
def test_raw_key_and_its_hash_never_reach_the_audit_trail(db_session, org, key_type):
    """The audit row records that a credential changed -- never the credential."""
    service = PatentScopedKeyService(db_session)
    first = service.provision_key(org.id, key_type, None)
    second = service.provision_key(org.id, key_type, None)

    db_session.expire_all()
    rows = _audit_rows(db_session, org.id)
    assert len(rows) == 2

    for row in rows:
        blob = _serialized(row)
        for secret in (first, second):
            assert secret not in blob, f"{row.action} leaked a raw key"
            assert PatentScopedKeyService.hash_key(secret) not in blob, (
                f"{row.action} leaked a key hash"
            )
