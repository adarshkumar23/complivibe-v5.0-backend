"""Deepened coverage for the PAM-sessions router (app/api/v1/pam_sessions.py).

Existing tests (test_pam_sessions_t42, test_g2_pam_session_denied_signal) cover
the ingest/upsert/patch/flag happy paths, the denied-signal preservation rules,
and time-ordering 422s. This file adds the gaps they leave:

  * permission enforcement -- technical_controls:view on the read endpoints
    (403 for a bespoke zero-permission persona, since every seeded role holds
    :view) and technical_controls:manage on the mutating endpoints (403 for
    auditor, which lacks :manage but holds :view).
  * an authorized read persona (readonly) getting 200 through the :view gate.
  * 404 on PATCH / flag-unapproved for an unknown session id.
  * the business rule that an *approved* PAM session cannot be flagged as
    unapproved (400).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.api.v1.pam_sessions import router as pam_sessions_router
from app.models.role import Role
from tests.helpers.auth_org import add_org_member, bootstrap_org_user

LINEAGE_CONFIG_URL = "/api/v1/data-observability/lineage/openmetadata/configure"
PAM_BASE = "/api/v1/pam/sessions"


def _ensure_pam_router(app) -> None:
    if not any(getattr(route, "path", None) == PAM_BASE for route in app.routes):
        app.include_router(pam_sessions_router, prefix="/api/v1")


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
        "raw_payload": {"event": "session.closed"},
    }
    payload.update(overrides)
    return payload


def _zero_permission_headers(db_session, client, organization_id: str, email: str) -> dict[str, str]:
    """A custom role holding no permissions -- the only way to hit the :view 403,
    since owner/admin/compliance_manager/reviewer/auditor/readonly all hold
    technical_controls:view."""
    role = Role(
        organization_id=uuid.UUID(organization_id),
        name=f"pam-zero-{uuid.uuid4().hex[:8]}",
        description="no permissions",
        is_system=False,
        is_system_role=False,
        is_active=True,
    )
    db_session.add(role)
    db_session.commit()
    return add_org_member(db_session, client, organization_id, email, role_name=role.name)


def test_list_requires_technical_controls_view(client, db_session, _test_app):
    _ensure_pam_router(_test_app)
    org = bootstrap_org_user(client, email_prefix="pam-cov-view")
    no_perms = _zero_permission_headers(db_session, client, org["organization_id"], "pam-cov-noperm@example.com")

    assert client.get(PAM_BASE, headers=no_perms).status_code == 403
    assert client.get(f"{PAM_BASE}/unapproved-risks", headers=no_perms).status_code == 403


def test_readonly_role_can_read_sessions(client, db_session, _test_app):
    # readonly holds technical_controls:view but not :manage -> reads succeed (200).
    _ensure_pam_router(_test_app)
    org = bootstrap_org_user(client, email_prefix="pam-cov-ro")
    readonly = add_org_member(db_session, client, org["organization_id"], "pam-cov-ro@example.com", role_name="readonly")

    listed = client.get(PAM_BASE, headers=readonly)
    assert listed.status_code == 200, listed.text
    assert listed.json() == []
    risks = client.get(f"{PAM_BASE}/unapproved-risks", headers=readonly)
    assert risks.status_code == 200, risks.text
    assert risks.json()["total_unapproved_sessions"] == 0


def test_mutations_require_technical_controls_manage(client, db_session, _test_app):
    # auditor holds :view but lacks :manage -> PATCH and flag are 403 (checked
    # before the body runs, so a random session id is fine).
    _ensure_pam_router(_test_app)
    org = bootstrap_org_user(client, email_prefix="pam-cov-manage")
    auditor = add_org_member(db_session, client, org["organization_id"], "pam-cov-auditor@example.com", role_name="auditor")
    sid = uuid.uuid4()

    assert client.patch(f"{PAM_BASE}/{sid}", headers=auditor, json={"risk_status": "accepted"}).status_code == 403
    assert client.post(f"{PAM_BASE}/{sid}/flag-unapproved", headers=auditor).status_code == 403


def test_patch_and_flag_unknown_session_returns_404(client, db_session, _test_app):
    _ensure_pam_router(_test_app)
    org = bootstrap_org_user(client, email_prefix="pam-cov-404")
    sid = uuid.uuid4()

    patched = client.patch(f"{PAM_BASE}/{sid}", headers=org["org_headers"], json={"risk_status": "accepted"})
    assert patched.status_code == 404, patched.text
    flagged = client.post(f"{PAM_BASE}/{sid}/flag-unapproved", headers=org["org_headers"])
    assert flagged.status_code == 404, flagged.text


def test_flagging_an_approved_session_is_rejected(client, db_session, _test_app):
    # Business rule: an approved privileged session cannot be flagged as unapproved.
    _ensure_pam_router(_test_app)
    org = bootstrap_org_user(client, email_prefix="pam-cov-approved")
    ingest_key = _configure_ingest_key(client, org["org_headers"], "pam-cov-approved-key-1")

    created = client.post(
        PAM_BASE,
        headers={"X-CompliVibe-Key": ingest_key},
        json=_session_payload("pam-cov-approved-1", approved_by="manager@example.com", approval_reference="CHG-99"),
    )
    assert created.status_code == 201, created.text
    assert created.json()["approval_status"] == "approved"
    session_id = created.json()["session_id"]

    rejected = client.post(f"{PAM_BASE}/{session_id}/flag-unapproved", headers=org["org_headers"])
    assert rejected.status_code == 400, rejected.text
    assert "Approved PAM sessions cannot be flagged" in rejected.json()["detail"]
