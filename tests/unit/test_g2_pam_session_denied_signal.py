from datetime import UTC, datetime
import uuid

from app.api.v1.pam_sessions import router as pam_sessions_router
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


def _configure_ingest_key(client, headers: dict[str, str], api_key: str) -> str:
    response = client.post(
        LINEAGE_CONFIG_URL,
        headers=headers,
        json={
            "base_url": "https://metadata.example.test",
            "jwt_token": "test-jwt-token",
            "org_api_key": api_key,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["ingest_api_key"]


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


def test_denied_session_is_included_in_unapproved_risks_view(client, db_session, _test_app):
    """BUG (a): the unapproved-risks view used to filter approval_status == 'missing'
    only, silently excluding sessions whose approval was actively 'denied' -- a denied
    session is a real, at-least-as-strong governance signal that must not be hidden.
    """
    _ensure_pam_router(_test_app)
    org = bootstrap_org_user(client, email_prefix="g2-pam-denied-view")
    _grant_pam_permissions(db_session, org["organization_id"], org["user_id"])
    ingest_key = _configure_ingest_key(client, org["org_headers"], "pam-key-denied-view-1")

    missing = client.post(
        PAM_BASE,
        headers={"X-CompliVibe-Key": ingest_key},
        json=_session_payload("pam-missing-signal"),
    )
    assert missing.status_code == 201
    assert missing.json()["approval_status"] == "missing"

    denied = client.post(
        PAM_BASE,
        headers={"X-CompliVibe-Key": ingest_key},
        json=_session_payload("pam-denied-signal", approval_status="denied"),
    )
    assert denied.status_code == 201
    assert denied.json()["approval_status"] == "denied"

    approved = client.post(
        PAM_BASE,
        headers={"X-CompliVibe-Key": ingest_key},
        json=_session_payload(
            "pam-approved-signal",
            approved_by="manager@example.com",
            approval_reference="CHG-1",
        ),
    )
    assert approved.status_code == 201
    assert approved.json()["approval_status"] == "approved"

    risk_list = client.get(f"{PAM_BASE}/unapproved-risks", headers=org["org_headers"])
    assert risk_list.status_code == 200
    body = risk_list.json()

    external_ids = {row["external_session_id"] for row in body["sessions"]}
    assert "pam-missing-signal" in external_ids
    assert "pam-denied-signal" in external_ids, "denied session must not be silently excluded"
    assert "pam-approved-signal" not in external_ids
    assert body["total_unapproved_sessions"] == 2


def test_flag_unapproved_preserves_denied_status_instead_of_overwriting_with_missing(client, db_session, _test_app):
    """BUG (b): flag_unapproved_session used to unconditionally set approval_status =
    'missing', which overwrote/destroyed an existing 'denied' status. The denied signal
    must survive being flagged.
    """
    _ensure_pam_router(_test_app)
    org = bootstrap_org_user(client, email_prefix="g2-pam-denied-flag")
    _grant_pam_permissions(db_session, org["organization_id"], org["user_id"])
    ingest_key = _configure_ingest_key(client, org["org_headers"], "pam-key-denied-flag-1")

    created = client.post(
        PAM_BASE,
        headers={"X-CompliVibe-Key": ingest_key},
        json=_session_payload("pam-denied-flag-target", approval_status="denied"),
    )
    assert created.status_code == 201
    assert created.json()["approval_status"] == "denied"
    session_id = created.json()["session_id"]

    flagged = client.post(f"{PAM_BASE}/{session_id}/flag-unapproved", headers=org["org_headers"])
    assert flagged.status_code == 200
    body = flagged.json()
    assert body["approval_status"] == "denied", "flagging must not downgrade 'denied' to 'missing'"
    assert body["risk_status"] == "open"
    assert body["flagged_by"] == org["user_id"]

    row = db_session.query(PAMSessionRecord).filter_by(external_session_id="pam-denied-flag-target").one()
    assert row.approval_status == "denied"


def test_flag_unapproved_still_normalizes_unknown_to_missing(client, db_session, _test_app):
    """Confirms the fix is targeted: a session with 'unknown' status (not 'denied')
    still gets normalized to 'missing' as before -- only 'denied' is preserved.
    """
    _ensure_pam_router(_test_app)
    org = bootstrap_org_user(client, email_prefix="g2-pam-unknown-flag")
    _grant_pam_permissions(db_session, org["organization_id"], org["user_id"])
    ingest_key = _configure_ingest_key(client, org["org_headers"], "pam-key-unknown-flag-1")

    created = client.post(
        PAM_BASE,
        headers={"X-CompliVibe-Key": ingest_key},
        json=_session_payload("pam-unknown-flag-target", approval_status="unknown", ended_at=None),
    )
    assert created.status_code == 201
    assert created.json()["approval_status"] == "unknown"
    session_id = created.json()["session_id"]

    flagged = client.post(f"{PAM_BASE}/{session_id}/flag-unapproved", headers=org["org_headers"])
    assert flagged.status_code == 200
    assert flagged.json()["approval_status"] == "missing"
