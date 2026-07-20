from datetime import UTC, datetime, timedelta
import uuid

from app.api.v1.pam_sessions import router as pam_sessions_router
from app.models.audit_log import AuditLog
from app.models.membership import Membership
from app.models.openmetadata_integration import OpenMetadataIntegration  # noqa: F401 - registers inbound key table
from app.models.pam_session_record import PAMSessionRecord  # noqa: F401 - registers PAM test table
from app.models.permission import Permission
from app.models.role_permission import RolePermission
from tests.helpers.auth_org import bootstrap_org_user

LINEAGE_CONFIG_URL = "/api/v1/data-observability/lineage/openmetadata/configure"
PAM_BASE = "/api/v1/pam/sessions"


def _ensure_pam_router(_test_app) -> None:
    route_paths = {getattr(route, "path", None) for route in _test_app.routes}
    if PAM_BASE not in route_paths:
        _test_app.include_router(pam_sessions_router, prefix="/api/v1")


def _grant_pam_permissions(db_session, org_id: str, user_id: str) -> None:
    membership = db_session.query(Membership).filter_by(
        organization_id=uuid.UUID(org_id),
        user_id=uuid.UUID(user_id),
    ).one()
    for code in ("pam_sessions:read", "pam_sessions:write"):
        permission = db_session.query(Permission).filter_by(key=code).one_or_none()
        if permission is None:
            permission = Permission(key=code, description=f"Test permission {code}")
            db_session.add(permission)
            db_session.flush()
        existing = db_session.query(RolePermission).filter_by(
            role_id=membership.role_id,
            permission_id=permission.id,
        ).one_or_none()
        if existing is None:
            db_session.add(RolePermission(role_id=membership.role_id, permission_id=permission.id))
    db_session.commit()


def _configure_ingest_key(client, headers: dict[str, str], api_key: str | None = None) -> str:
    # PAM now has its OWN ingest key (key_type "pam"); it no longer shares the
    # OpenMetadata/lineage key. api_key is ignored (the endpoint mints a random key).
    response = client.post(
        "/api/v1/integrations/ingest-keys",
        headers=headers,
        json={"key_type": "pam"},
    )
    assert response.status_code == 201, response.text
    return response.json()["api_key"]


def _session_payload(external_session_id: str, **overrides):
    payload = {
        "external_session_id": external_session_id,
        "pam_provider": "teleport",
        "identity": "alice@example.com",
        "privileged_account": "root",
        "target_system": "prod-db-01",
        "target_resource_type": "database",
        "started_at": datetime(2026, 7, 5, 12, 0, tzinfo=UTC).isoformat(),
        "ended_at": datetime(2026, 7, 5, 12, 30, tzinfo=UTC).isoformat(),
        "session_recording_url": "https://recordings.example.test/sess-1",
        "raw_payload": {"event": "session.closed"},
    }
    payload.update(overrides)
    return payload


def test_t42_api_key_ingest_marks_missing_approval_as_real_risk(client, db_session, _test_app):
    _ensure_pam_router(_test_app)
    org = bootstrap_org_user(client, email_prefix="t42-pam-ingest")
    _grant_pam_permissions(db_session, org["organization_id"], org["user_id"])
    ingest_key = _configure_ingest_key(client, org["org_headers"], "pam-key-123456789")

    invalid = client.post(PAM_BASE, headers={"X-CompliVibe-Key": "wrong-key"}, json=_session_payload("pam-invalid"))
    assert invalid.status_code == 401

    created = client.post(PAM_BASE, headers={"X-CompliVibe-Key": ingest_key}, json=_session_payload("pam-missing-1"))
    assert created.status_code == 201
    body = created.json()
    assert body["approval_status"] == "missing"
    assert body["risk_status"] == "open"
    assert body["risk_reason"] == "Privileged session has no approval evidence"
    assert body["created"] is True

    risk_list = client.get(f"{PAM_BASE}/unapproved-risks", headers=org["org_headers"])
    assert risk_list.status_code == 200
    risk_body = risk_list.json()
    assert risk_body["total_unapproved_sessions"] == 1
    assert risk_body["open_risk_sessions"] == 1
    assert risk_body["sessions"][0]["external_session_id"] == "pam-missing-1"

    stored = db_session.query(PAMSessionRecord).filter_by(external_session_id="pam-missing-1").one()
    assert stored.organization_id == uuid.UUID(org["organization_id"])
    assert stored.approved_by is None
    assert stored.session_recording_url == "https://recordings.example.test/sess-1"

    audit = db_session.query(AuditLog).filter_by(entity_id=stored.id, action="pam_session.ingested").one()
    assert audit.actor_user_id is None
    assert audit.metadata_json["source"] == "api_key_ingest"
    assert audit.after_json["risk_status"] == "open"


def test_t42_ingest_upserts_and_authenticated_state_changes_are_audited(client, db_session, _test_app):
    _ensure_pam_router(_test_app)
    org = bootstrap_org_user(client, email_prefix="t42-pam-update")
    _grant_pam_permissions(db_session, org["organization_id"], org["user_id"])
    ingest_key = _configure_ingest_key(client, org["org_headers"], "pam-key-987654321")

    first = client.post(
        PAM_BASE,
        headers={"X-CompliVibe-Key": ingest_key},
        json=_session_payload("pam-upsert-1", approval_status="unknown", ended_at=None),
    )
    assert first.status_code == 201
    assert first.json()["risk_status"] == "monitor"

    second = client.post(
        PAM_BASE,
        headers={"X-CompliVibe-Key": ingest_key},
        json=_session_payload(
            "pam-upsert-1",
            approved_by="manager@example.com",
            approval_reference="CHG-42",
            raw_payload={"event": "session.approved"},
        ),
    )
    assert second.status_code == 201
    assert second.json()["created"] is False
    assert second.json()["approval_status"] == "approved"
    assert second.json()["risk_status"] == "monitor"

    row = db_session.query(PAMSessionRecord).filter_by(external_session_id="pam-upsert-1").one()
    assert row.approved_by == "manager@example.com"
    assert row.approval_reference == "CHG-42"
    assert db_session.query(PAMSessionRecord).filter_by(external_session_id="pam-upsert-1").count() == 1

    updated = client.patch(
        f"{PAM_BASE}/{row.id}",
        headers=org["org_headers"],
        json={"approval_status": "missing", "approved_by": None, "approval_reference": None},
    )
    assert updated.status_code == 200
    assert updated.json()["approval_status"] == "missing"
    assert updated.json()["risk_status"] == "open"

    flagged = client.post(f"{PAM_BASE}/{row.id}/flag-unapproved", headers=org["org_headers"])
    assert flagged.status_code == 200
    flagged_body = flagged.json()
    assert flagged_body["risk_status"] == "open"
    assert flagged_body["flagged_by"] == org["user_id"]
    assert flagged_body["flagged_at"] is not None

    actions = [audit.action for audit in db_session.query(AuditLog).filter_by(entity_id=row.id).all()]
    assert "pam_session.ingested" in actions
    assert "pam_session.ingest_updated" in actions
    assert "pam_session.updated" in actions
    assert "pam_session.unapproved_flagged" in actions


def test_t42_validation_and_tenant_scoping(client, db_session, _test_app):
    _ensure_pam_router(_test_app)
    org1 = bootstrap_org_user(client, email_prefix="t42-pam-a")
    org2 = bootstrap_org_user(client, email_prefix="t42-pam-b")
    _grant_pam_permissions(db_session, org1["organization_id"], org1["user_id"])
    _grant_pam_permissions(db_session, org2["organization_id"], org2["user_id"])
    key1 = _configure_ingest_key(client, org1["org_headers"], "pam-key-a-123456")
    key2 = _configure_ingest_key(client, org2["org_headers"], "pam-key-b-123456")

    bad_time = client.post(
        PAM_BASE,
        headers={"X-CompliVibe-Key": key1},
        json=_session_payload(
            "pam-bad-time",
            started_at=datetime(2026, 7, 5, 13, 0, tzinfo=UTC).isoformat(),
            ended_at=datetime(2026, 7, 5, 12, 59, tzinfo=UTC).isoformat(),
        ),
    )
    assert bad_time.status_code == 422

    org1_create = client.post(PAM_BASE, headers={"X-CompliVibe-Key": key1}, json=_session_payload("pam-org-1"))
    assert org1_create.status_code == 201
    org2_create = client.post(PAM_BASE, headers={"X-CompliVibe-Key": key2}, json=_session_payload("pam-org-2", identity="bob@example.com"))
    assert org2_create.status_code == 201

    org1_list = client.get(PAM_BASE, headers=org1["org_headers"])
    assert org1_list.status_code == 200
    assert [item["external_session_id"] for item in org1_list.json()] == ["pam-org-1"]

    org2_list = client.get(PAM_BASE, headers=org2["org_headers"])
    assert org2_list.status_code == 200
    assert [item["external_session_id"] for item in org2_list.json()] == ["pam-org-2"]

    too_early = (datetime(2026, 7, 5, 11, 0, tzinfo=UTC) - timedelta(minutes=1)).isoformat()
    bad_update = client.patch(
        f"{PAM_BASE}/{org1_create.json()['session_id']}",
        headers=org1["org_headers"],
        json={"ended_at": too_early},
    )
    assert bad_update.status_code == 422
