"""Audit trail for subsystem inbound-ingest key provisioning/rotation (2026-07-20).

Subsystem ingest keys are PAM-class credentials: whoever holds one can push inbound
telemetry for a whole subsystem of an organization. Before this fix, minting one and
rotating one both wrote a live credential with ZERO audit trail -- no record of who
provisioned it, when, for which org, or for which subsystem.

These tests assert the audit rows exist for both the create and the rotate path, and
that the raw key value never appears anywhere in the audit record.
"""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import select

from app.models.audit_log import AuditLog
from tests.helpers.auth_org import bootstrap_org_user

INGEST_KEYS = "/api/v1/integrations/ingest-keys"


def _key_audit_rows(db_session, org_id: str) -> list[AuditLog]:
    rows = db_session.execute(
        select(AuditLog)
        .where(
            AuditLog.organization_id == UUID(org_id),
            AuditLog.entity_type == "subsystem_ingest_keys",
        )
        .order_by(AuditLog.created_at.asc())
    ).scalars().all()
    return list(rows)


def test_provisioning_a_subsystem_ingest_key_is_audited(client, db_session):
    org = bootstrap_org_user(client, email_prefix="sik-audit-prov")
    resp = client.post(INGEST_KEYS, headers=org["org_headers"], json={"key_type": "pam"})
    assert resp.status_code == 201, resp.text
    raw_key = resp.json()["api_key"]

    db_session.expire_all()
    rows = _key_audit_rows(db_session, org["organization_id"])
    assert len(rows) == 1, "provisioning a PAM-class ingest key must leave an audit trail"
    row = rows[0]
    assert row.action == "subsystem_ingest_key.provisioned"
    assert row.organization_id == UUID(org["organization_id"])
    assert row.actor_user_id == UUID(org["user_id"])
    assert row.metadata_json["key_type"] == "pam"
    assert row.created_at is not None

    # The credential itself must never be written into the audit trail.
    serialized = json.dumps(
        {"m": row.metadata_json, "b": row.before_json, "a": row.after_json}, default=str
    )
    assert raw_key not in serialized


def test_rotating_a_subsystem_ingest_key_is_audited_as_a_rotation(client, db_session):
    org = bootstrap_org_user(client, email_prefix="sik-audit-rot")
    first = client.post(INGEST_KEYS, headers=org["org_headers"], json={"key_type": "pam"})
    assert first.status_code == 201, first.text
    second = client.post(INGEST_KEYS, headers=org["org_headers"], json={"key_type": "pam"})
    assert second.status_code == 201, second.text
    assert second.json()["api_key"] != first.json()["api_key"]

    db_session.expire_all()
    rows = _key_audit_rows(db_session, org["organization_id"])
    assert len(rows) == 2, "rotation must be audited separately from initial provisioning"
    assert [r.action for r in rows] == [
        "subsystem_ingest_key.provisioned",
        "subsystem_ingest_key.rotated",
    ]
    rotation = rows[1]
    assert rotation.metadata_json["key_type"] == "pam"
    assert rotation.actor_user_id == UUID(org["user_id"])
    serialized = json.dumps(
        {"m": rotation.metadata_json, "b": rotation.before_json, "a": rotation.after_json},
        default=str,
    )
    assert second.json()["api_key"] not in serialized
    assert first.json()["api_key"] not in serialized


def test_key_types_are_audited_independently(client, db_session):
    org = bootstrap_org_user(client, email_prefix="sik-audit-types")
    for key_type in ("pam", "cookies"):
        assert (
            client.post(INGEST_KEYS, headers=org["org_headers"], json={"key_type": key_type}).status_code
            == 201
        )

    db_session.expire_all()
    rows = _key_audit_rows(db_session, org["organization_id"])
    assert [r.action for r in rows] == [
        "subsystem_ingest_key.provisioned",
        "subsystem_ingest_key.provisioned",
    ]
    assert sorted(r.metadata_json["key_type"] for r in rows) == ["cookies", "pam"]
