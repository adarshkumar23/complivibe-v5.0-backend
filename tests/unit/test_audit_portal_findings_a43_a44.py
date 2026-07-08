from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import uuid

from app.core.security import get_password_hash
from app.models.audit_log import AuditLog
from app.models.auditor_portal_invitation import AuditorPortalInvitation
from app.models.control import Control
from app.models.evidence_item import EvidenceItem
from app.models.membership import Membership
from app.models.obligation import Obligation
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user, login_user, org_headers

ENGAGEMENT_BASE = "/api/v1/compliance/audit-engagements"
PORTAL_BASE = "/api/v1/audit-portal"
FINDINGS_BASE = "/api/v1/compliance/audit-findings"


def _framework_ids(client, headers: dict[str, str]) -> tuple[str, str]:
    resp = client.get("/api/v1/frameworks", headers=headers)
    assert resp.status_code == 200
    frameworks = resp.json()
    assert len(frameworks) >= 2
    return frameworks[0]["id"], frameworks[1]["id"]


def _create_active_user_with_role(db_session, org_id: str, email: str, role_name: str = "reviewer") -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0],
        hashed_password=get_password_hash("Pass1234!@"),
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    db_session.flush()

    role = db_session.query(Role).filter(Role.organization_id == uuid.UUID(org_id), Role.name == role_name).one()
    db_session.add(
        Membership(
            organization_id=uuid.UUID(org_id),
            user_id=user.id,
            role_id=role.id,
            status="active",
        )
    )
    db_session.commit()
    return user


def _create_engagement(client, headers: dict[str, str], framework_id: str, auditor_user_id: str, title: str = "Portal Audit") -> dict:
    resp = client.post(
        ENGAGEMENT_BASE,
        headers=headers,
        json={
            "title": title,
            "audit_type": "external_certification",
            "scope_framework_ids": [framework_id],
            "assigned_auditor_ids": [auditor_user_id],
            "start_date": (date.today() + timedelta(days=2)).isoformat(),
            "end_date": (date.today() + timedelta(days=30)).isoformat(),
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _create_control(client, headers: dict[str, str], title: str) -> dict:
    resp = client.post(
        "/api/v1/controls",
        headers=headers,
        json={
            "title": title,
            "description": "desc",
            "control_type": "process",
            "criticality": "medium",
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _create_obligation(db_session, framework_id: str, reference_code: str) -> Obligation:
    row = Obligation(
        framework_id=uuid.UUID(framework_id),
        reference_code=reference_code,
        title=f"Obligation {reference_code}",
        description="seeded for test",
        jurisdiction="US",
        status="active",
    )
    db_session.add(row)
    db_session.commit()
    return row


def _create_evidence(client, headers: dict[str, str], title: str) -> dict:
    resp = client.post(
        "/api/v1/evidence",
        headers=headers,
        json={"title": title, "evidence_type": "other"},
    )
    assert resp.status_code == 201
    return resp.json()


def _create_invitation(client, headers: dict[str, str], engagement_id: str, payload: dict) -> dict:
    resp = client.post(f"{PORTAL_BASE}/invitations?engagement_id={engagement_id}", headers=headers, json=payload)
    assert resp.status_code == 201
    return resp.json()


def _create_risk(client, headers: dict[str, str], title: str) -> dict:
    resp = client.post(
        "/api/v1/risks",
        headers=headers,
        json={
            "title": title,
            "description": "desc",
            "category": "other",
            "likelihood": 3,
            "impact": 4,
            "treatment_strategy": "mitigate",
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _create_finding(client, headers: dict[str, str], engagement_id: str, owner_id: str, **overrides) -> dict:
    body = {
        "severity": "high",
        "framework_ref": "SOC2 CC6.1",
        "title": "Finding",
        "description": "Detailed finding",
        "assigned_owner_id": owner_id,
        "remediation_action": "Fix issue",
        "target_remediation_date": (date.today() + timedelta(days=10)).isoformat(),
        "risk_register_entry_id": None,
        "control_id": None,
    }
    body.update(overrides)
    resp = client.post(f"{FINDINGS_BASE}?engagement_id={engagement_id}", headers=headers, json=body)
    assert resp.status_code == 201
    return resp.json()


def test_a43_create_invitation_returns_plaintext_token_and_get_does_not(client):
    org = bootstrap_org_user(client, email_prefix="a43-invite")
    fw1, _ = _framework_ids(client, org["headers"])
    engagement = _create_engagement(client, org["org_headers"], fw1, org["user_id"])

    created = _create_invitation(
        client,
        org["org_headers"],
        engagement["id"],
        {
            "auditor_email": "auditor@example.com",
            "auditor_name": "Auditor",
            "scoped_framework_ids": [fw1],
            "expires_in_days": 30,
        },
    )
    assert created["plaintext_token"]
    assert created["warning"]
    assert created["framework_id"] == fw1

    detail = client.get(f"{PORTAL_BASE}/invitations/{created['invitation_id']}", headers=org["org_headers"])
    assert detail.status_code == 200
    payload = detail.json()
    assert "plaintext_token" not in payload
    assert "token_hash" not in payload
    assert payload["framework_id"] == fw1
    assert payload["scoped_framework_ids"] == [fw1]


def test_a43_portal_auth_valid_expired_revoked_and_access_count(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a43-auth")
    fw1, _ = _framework_ids(client, org["headers"])
    engagement = _create_engagement(client, org["org_headers"], fw1, org["user_id"])

    created = _create_invitation(
        client,
        org["org_headers"],
        engagement["id"],
        {
            "auditor_email": "token-auditor@example.com",
            "scoped_framework_ids": [fw1],
            "expires_in_days": 30,
        },
    )
    token = created["plaintext_token"]
    portal_headers = {"Authorization": f"Bearer {token}"}

    first = client.get(f"{PORTAL_BASE}/me", headers=portal_headers)
    assert first.status_code == 200
    second = client.get(f"{PORTAL_BASE}/me", headers=portal_headers)
    assert second.status_code == 200
    assert second.json()["access_count"] == 2

    detail = client.get(f"{PORTAL_BASE}/invitations/{created['invitation_id']}", headers=org["org_headers"])
    assert detail.status_code == 200
    assert detail.json()["last_accessed_at"] is not None
    assert detail.json()["access_count"] == 2

    expired_invite = _create_invitation(
        client,
        org["org_headers"],
        engagement["id"],
        {
            "auditor_email": "expired@example.com",
            "scoped_framework_ids": [fw1],
            "expires_in_days": 1,
        },
    )
    expired_row = db_session.query(AuditorPortalInvitation).filter_by(id=uuid.UUID(expired_invite["invitation_id"])).one()
    expired_row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    expired_row.status = "active"
    db_session.commit()

    expired = client.get(
        f"{PORTAL_BASE}/me",
        headers={"Authorization": f"Bearer {expired_invite['plaintext_token']}"},
    )
    assert expired.status_code == 401

    refreshed = db_session.query(AuditorPortalInvitation).filter_by(id=expired_row.id).one()
    assert refreshed.status == "expired"

    revoked_invite = _create_invitation(
        client,
        org["org_headers"],
        engagement["id"],
        {
            "auditor_email": "revoked@example.com",
            "scoped_framework_ids": [fw1],
            "expires_in_days": 30,
        },
    )
    revoke = client.post(f"{PORTAL_BASE}/invitations/{revoked_invite['invitation_id']}/revoke", headers=org["org_headers"])
    assert revoke.status_code == 200

    revoked = client.get(
        f"{PORTAL_BASE}/me",
        headers={"Authorization": f"Bearer {revoked_invite['plaintext_token']}"},
    )
    assert revoked.status_code == 401


def test_a43_portal_controls_and_evidence_scoping_and_org_isolation(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="a43-scope-a")
    org_b = bootstrap_org_user(client, email_prefix="a43-scope-b")

    fw_in_scope, fw_out_scope = _framework_ids(client, org_a["headers"])
    engagement = _create_engagement(client, org_a["org_headers"], fw_in_scope, org_a["user_id"])

    ob_in = _create_obligation(db_session, fw_in_scope, "A43-IN")
    ob_out = _create_obligation(db_session, fw_out_scope, "A43-OUT")

    c_in = _create_control(client, org_a["org_headers"], "Scoped control")
    c_out = _create_control(client, org_a["org_headers"], "Out-of-scope control")
    c_org_b = _create_control(client, org_b["org_headers"], "Other org control")

    # Real control<->obligation membership is tracked via ControlObligationMapping
    # (POST /controls/{id}/obligations), not the legacy Control.obligation_id FK,
    # which no API path writes to. Activate both frameworks for org_a first since
    # mapping requires the obligation's framework to be active in-org.
    for fw_id in (fw_in_scope, fw_out_scope):
        activate = client.post(f"/api/v1/frameworks/{fw_id}/activate", headers=org_a["org_headers"], json={})
        assert activate.status_code == 200
    activate_b = client.post(f"/api/v1/frameworks/{fw_in_scope}/activate", headers=org_b["org_headers"], json={})
    assert activate_b.status_code == 200

    map_in = client.post(
        f"/api/v1/controls/{c_in['id']}/obligations",
        headers=org_a["org_headers"],
        json={"obligation_id": str(ob_in.id), "mapping_type": "satisfies"},
    )
    assert map_in.status_code == 200
    map_out = client.post(
        f"/api/v1/controls/{c_out['id']}/obligations",
        headers=org_a["org_headers"],
        json={"obligation_id": str(ob_out.id), "mapping_type": "satisfies"},
    )
    assert map_out.status_code == 200
    map_b = client.post(
        f"/api/v1/controls/{c_org_b['id']}/obligations",
        headers=org_b["org_headers"],
        json={"obligation_id": str(ob_in.id), "mapping_type": "satisfies"},
    )
    assert map_b.status_code == 200

    ev_in = _create_evidence(client, org_a["org_headers"], "Scoped evidence")
    ev_out = _create_evidence(client, org_a["org_headers"], "Other evidence")

    link1 = client.post(
        f"/api/v1/evidence/{ev_in['id']}/controls",
        headers=org_a["org_headers"],
        json={"control_id": c_in["id"], "confidence": "manual_confirmed"},
    )
    assert link1.status_code == 200

    link2 = client.post(
        f"/api/v1/evidence/{ev_out['id']}/controls",
        headers=org_a["org_headers"],
        json={"control_id": c_out["id"], "confidence": "manual_confirmed"},
    )
    assert link2.status_code == 200

    invitation = _create_invitation(
        client,
        org_a["org_headers"],
        engagement["id"],
        {
            "auditor_email": "scope-auditor@example.com",
            "scoped_framework_ids": [fw_in_scope],
            "scoped_evidence_ids": [ev_in["id"]],
            "expires_in_days": 30,
        },
    )
    portal_headers = {"Authorization": f"Bearer {invitation['plaintext_token']}"}

    controls = client.get(f"{PORTAL_BASE}/controls", headers=portal_headers)
    assert controls.status_code == 200
    ids = {row["id"] for row in controls.json()}
    assert c_in["id"] in ids
    assert c_out["id"] not in ids
    assert c_org_b["id"] not in ids

    evidence = client.get(f"{PORTAL_BASE}/evidence", headers=portal_headers)
    assert evidence.status_code == 200
    evidence_ids = {row["id"] for row in evidence.json()}
    assert evidence_ids == {ev_in["id"]}


def test_a43_portal_evidence_uses_original_created_at_for_imported_records(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a43-evidence-dates")
    fw_in_scope, _ = _framework_ids(client, org["headers"])
    engagement = _create_engagement(client, org["org_headers"], fw_in_scope, org["user_id"])

    manual_resp = client.post(
        "/api/v1/evidence",
        headers=org["org_headers"],
        json={
            "title": "Manual Evidence Date",
            "evidence_type": "document",
            "collected_at": "2025-01-15T12:00:00Z",
        },
    )
    assert manual_resp.status_code == 201
    manual_id = manual_resp.json()["id"]

    imported_resp = client.post(
        "/api/v1/evidence",
        headers=org["org_headers"],
        json={"title": "Imported Evidence Date", "evidence_type": "document"},
    )
    assert imported_resp.status_code == 201
    imported_id = imported_resp.json()["id"]

    imported_row = db_session.query(EvidenceItem).filter(EvidenceItem.id == uuid.UUID(imported_id)).one()
    imported_row.source = "imported"
    imported_row.source_import_tool = "drata"
    imported_row.original_created_at = datetime(2021, 6, 10, 9, 30, tzinfo=UTC)
    db_session.commit()

    invitation = _create_invitation(
        client,
        org["org_headers"],
        engagement["id"],
        {
            "auditor_email": "dates-auditor@example.com",
            "scoped_framework_ids": [fw_in_scope],
            "scoped_evidence_ids": [manual_id, imported_id],
            "expires_in_days": 30,
        },
    )
    portal_headers = {"Authorization": f"Bearer {invitation['plaintext_token']}"}

    evidence = client.get(f"{PORTAL_BASE}/evidence", headers=portal_headers)
    assert evidence.status_code == 200
    evidence_map = {row["id"]: row for row in evidence.json()}

    assert evidence_map[manual_id]["submitted_at"] == "2025-01-15T12:00:00"
    assert evidence_map[imported_id]["submitted_at"] == "2021-06-10T09:30:00"


def test_a43_portal_view_writes_resource_specific_audit_trail(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a43-viewaudit")
    fw_in_scope, _ = _framework_ids(client, org["headers"])
    engagement = _create_engagement(client, org["org_headers"], fw_in_scope, org["user_id"])

    invitation = _create_invitation(
        client,
        org["org_headers"],
        engagement["id"],
        {
            "auditor_email": "view-auditor@example.com",
            "scoped_framework_ids": [fw_in_scope],
            "expires_in_days": 30,
        },
    )
    portal_headers = {"Authorization": f"Bearer {invitation['plaintext_token']}"}
    invitation_id = uuid.UUID(invitation["invitation_id"])

    assert client.get(f"{PORTAL_BASE}/me", headers=portal_headers).status_code == 200
    assert client.get(f"{PORTAL_BASE}/controls", headers=portal_headers).status_code == 200
    assert client.get(f"{PORTAL_BASE}/evidence", headers=portal_headers).status_code == 200
    assert client.get(f"{PORTAL_BASE}/reports", headers=portal_headers).status_code == 200

    logs = (
        db_session.query(AuditLog)
        .filter(AuditLog.entity_id == invitation_id, AuditLog.action == "auditor_portal.data_viewed")
        .all()
    )
    resource_types = {log.after_json["resource_type"] for log in logs}
    # Each scoped-data endpoint gets its own audit entry -- distinguishable from the
    # generic "auditor_portal.access" login-level entry written on every token auth.
    assert resource_types == {"engagement_summary", "controls", "evidence", "reports"}
    for log in logs:
        assert "item_count" in log.after_json
        assert "item_ids" in log.after_json

    access_logs = (
        db_session.query(AuditLog)
        .filter(AuditLog.entity_id == invitation_id, AuditLog.action == "auditor_portal.access")
        .all()
    )
    assert len(access_logs) == 4


def test_a43_portal_auth_error_messages_distinguish_invalid_expired_revoked(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a43-msgs")
    fw_in_scope, _ = _framework_ids(client, org["headers"])
    engagement = _create_engagement(client, org["org_headers"], fw_in_scope, org["user_id"])

    garbage = client.get(f"{PORTAL_BASE}/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert garbage.status_code == 401
    assert garbage.json()["detail"] == "Invalid portal token"

    expired_invite = _create_invitation(
        client,
        org["org_headers"],
        engagement["id"],
        {"auditor_email": "msg-expired@example.com", "scoped_framework_ids": [fw_in_scope], "expires_in_days": 1},
    )
    expired_row = db_session.query(AuditorPortalInvitation).filter_by(id=uuid.UUID(expired_invite["invitation_id"])).one()
    expired_row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()

    expired = client.get(
        f"{PORTAL_BASE}/me",
        headers={"Authorization": f"Bearer {expired_invite['plaintext_token']}"},
    )
    assert expired.status_code == 401
    assert expired.json()["detail"] == "Portal token expired"

    revoked_invite = _create_invitation(
        client,
        org["org_headers"],
        engagement["id"],
        {"auditor_email": "msg-revoked@example.com", "scoped_framework_ids": [fw_in_scope], "expires_in_days": 30},
    )
    client.post(f"{PORTAL_BASE}/invitations/{revoked_invite['invitation_id']}/revoke", headers=org["org_headers"])

    revoked = client.get(
        f"{PORTAL_BASE}/me",
        headers={"Authorization": f"Bearer {revoked_invite['plaintext_token']}"},
    )
    assert revoked.status_code == 401
    assert revoked.json()["detail"] == "Portal token revoked"

    # All three messages are distinct -- an auditor (or support engineer) can tell
    # apart "never existed"/"malformed" vs "expired mid-session" vs "explicitly revoked".
    assert len({garbage.json()["detail"], expired.json()["detail"], revoked.json()["detail"]}) == 3


def test_a44_finding_ref_generation_and_org_sequences(client):
    org_a = bootstrap_org_user(client, email_prefix="a44-ref-a")
    org_b = bootstrap_org_user(client, email_prefix="a44-ref-b")
    fw1, _ = _framework_ids(client, org_a["headers"])

    engagement_a = _create_engagement(client, org_a["org_headers"], fw1, org_a["user_id"], title="A44 A")
    engagement_b = _create_engagement(client, org_b["org_headers"], fw1, org_b["user_id"], title="A44 B")

    f1 = _create_finding(client, org_a["org_headers"], engagement_a["id"], org_a["user_id"], title="A1")
    f2 = _create_finding(client, org_a["org_headers"], engagement_a["id"], org_a["user_id"], title="A2")
    f3 = _create_finding(client, org_b["org_headers"], engagement_b["id"], org_b["user_id"], title="B1")

    year = datetime.now(UTC).year
    assert f1["finding_ref"] == f"F-{year}-001"
    assert f2["finding_ref"] == f"F-{year}-002"
    assert f3["finding_ref"] == f"F-{year}-001"


def test_a44_status_transitions_close_fields_and_invalid_transition(client):
    org = bootstrap_org_user(client, email_prefix="a44-transitions")
    fw1, _ = _framework_ids(client, org["headers"])
    engagement = _create_engagement(client, org["org_headers"], fw1, org["user_id"])
    finding = _create_finding(client, org["org_headers"], engagement["id"], org["user_id"])

    for next_status in ["in_remediation", "remediated", "closed"]:
        resp = client.post(
            f"{FINDINGS_BASE}/{finding['id']}/transition",
            headers=org["org_headers"],
            json={"new_status": next_status},
        )
        assert resp.status_code == 200
        finding = resp.json()

    assert finding["closed_at"] is not None

    invalid = client.post(
        f"{FINDINGS_BASE}/{finding['id']}/transition",
        headers=org["org_headers"],
        json={"new_status": "open"},
    )
    assert invalid.status_code == 422


def test_a44_link_to_risk_validation_bulk_transition_summary_and_soft_delete(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="a44-link-a")
    org_b = bootstrap_org_user(client, email_prefix="a44-link-b")
    fw1, _ = _framework_ids(client, org_a["headers"])
    engagement = _create_engagement(client, org_a["org_headers"], fw1, org_a["user_id"])

    risk_a = _create_risk(client, org_a["org_headers"], "Risk A")
    risk_b = _create_risk(client, org_b["org_headers"], "Risk B")

    overdue_date = (date.today() - timedelta(days=1)).isoformat()
    finding1 = _create_finding(
        client,
        org_a["org_headers"],
        engagement["id"],
        org_a["user_id"],
        title="Overdue finding",
        severity="critical",
        target_remediation_date=overdue_date,
    )
    finding2 = _create_finding(client, org_a["org_headers"], engagement["id"], org_a["user_id"], title="Second finding")

    linked = client.post(
        f"{FINDINGS_BASE}/{finding1['id']}/link-risk",
        headers=org_a["org_headers"],
        json={"risk_id": risk_a["id"]},
    )
    assert linked.status_code == 200
    assert linked.json()["risk_register_entry_id"] == risk_a["id"]

    cross_org = client.post(
        f"{FINDINGS_BASE}/{finding1['id']}/link-risk",
        headers=org_a["org_headers"],
        json={"risk_id": risk_b["id"]},
    )
    assert cross_org.status_code == 422

    closed = client.post(
        f"{FINDINGS_BASE}/{finding2['id']}/transition",
        headers=org_a["org_headers"],
        json={"new_status": "closed"},
    )
    assert closed.status_code == 200

    bulk = client.post(
        f"{FINDINGS_BASE}/bulk-transition",
        headers=org_a["org_headers"],
        json={"finding_ids": [finding1["id"], finding2["id"]], "new_status": "in_remediation"},
    )
    assert bulk.status_code == 200
    body = bulk.json()
    assert body["updated_count"] == 1
    assert finding2["id"] in body["failed_ids"]

    summary = client.get(f"{FINDINGS_BASE}/summary", headers=org_a["org_headers"])
    assert summary.status_code == 200
    summary_json = summary.json()
    assert summary_json["overdue_count"] >= 1

    block_delete = client.delete(f"{FINDINGS_BASE}/{finding1['id']}", headers=org_a["org_headers"])
    assert block_delete.status_code == 422

    open_finding = _create_finding(client, org_a["org_headers"], engagement["id"], org_a["user_id"], title="Delete me")
    allow_delete = client.delete(f"{FINDINGS_BASE}/{open_finding['id']}", headers=org_a["org_headers"])
    assert allow_delete.status_code == 200


def test_a43_non_admin_cannot_create_invitation(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a43-admin-check")
    fw1, _ = _framework_ids(client, org["headers"])
    engagement = _create_engagement(client, org["org_headers"], fw1, org["user_id"])

    reviewer = _create_active_user_with_role(db_session, org["organization_id"], "a43-reviewer@example.com", "reviewer")
    reviewer_headers = org_headers(login_user(client, reviewer.email), org["organization_id"])

    denied = client.post(
        f"{PORTAL_BASE}/invitations?engagement_id={engagement['id']}",
        headers=reviewer_headers,
        json={
            "auditor_email": "denied@example.com",
            "scoped_framework_ids": [fw1],
            "expires_in_days": 30,
        },
    )
    assert denied.status_code == 403


def test_a43_scoped_framework_ids_must_be_within_engagement_scope(client, db_session):
    """Regression: framework-based scoping must inherit and stay contained within the
    parent engagement's own scope_framework_ids, so an invitation can never grant an
    auditor visibility into frameworks the engagement itself was never scoped to."""
    org = bootstrap_org_user(client, email_prefix="a43-inherit")
    fw_in_scope, fw_out_of_scope = _framework_ids(client, org["headers"])
    engagement = _create_engagement(client, org["org_headers"], fw_in_scope, org["user_id"])

    # Explicitly requesting a framework outside the engagement's own scope is rejected.
    rejected = client.post(
        f"{PORTAL_BASE}/invitations?engagement_id={engagement['id']}",
        headers=org["org_headers"],
        json={
            "auditor_email": "overscope@example.com",
            "scoped_framework_ids": [fw_out_of_scope],
            "expires_in_days": 30,
        },
    )
    assert rejected.status_code == 422

    # Omitting scoped_framework_ids ("default" scoping) inherits the engagement's own
    # scope rather than defaulting to an empty/unbounded list.
    default_scoped = _create_invitation(
        client,
        org["org_headers"],
        engagement["id"],
        {
            "auditor_email": "default-scope@example.com",
            "expires_in_days": 30,
        },
    )
    detail = client.get(f"{PORTAL_BASE}/invitations/{default_scoped['invitation_id']}", headers=org["org_headers"])
    assert detail.status_code == 200
    assert detail.json()["scoped_framework_ids"] == [fw_in_scope]
    assert detail.json()["framework_id"] == fw_in_scope


def test_a43_explicit_scoped_control_ids_must_resolve_within_engagement_framework_scope(client, db_session):
    """Regression: explicit scoped_control_ids bypassed framework-containment validation
    entirely (only an org-id check was performed), which meant an admin could hand an
    auditor invitation direct visibility into controls from frameworks the parent
    engagement was never scoped to. Explicit control ids must now resolve (via their
    obligation's framework) to a framework within the engagement's own scope."""
    org = bootstrap_org_user(client, email_prefix="a43-control-containment")
    fw_in_scope, fw_out_of_scope = _framework_ids(client, org["headers"])
    engagement = _create_engagement(client, org["org_headers"], fw_in_scope, org["user_id"])

    ob_in = _create_obligation(db_session, fw_in_scope, "A43-CTRL-IN")
    ob_out = _create_obligation(db_session, fw_out_of_scope, "A43-CTRL-OUT")

    c_in = _create_control(client, org["org_headers"], "In-scope control")
    c_out = _create_control(client, org["org_headers"], "Out-of-scope control")
    c_unlinked = _create_control(client, org["org_headers"], "Unlinked control")

    row_in = db_session.query(Control).filter_by(id=uuid.UUID(c_in["id"])).one()
    row_out = db_session.query(Control).filter_by(id=uuid.UUID(c_out["id"])).one()
    row_in.obligation_id = ob_in.id
    row_out.obligation_id = ob_out.id
    db_session.commit()

    # A control whose framework is out of the engagement's scope must be rejected.
    rejected = client.post(
        f"{PORTAL_BASE}/invitations?engagement_id={engagement['id']}",
        headers=org["org_headers"],
        json={
            "auditor_email": "control-overscope@example.com",
            "scoped_control_ids": [c_out["id"]],
            "expires_in_days": 30,
        },
    )
    assert rejected.status_code == 422

    # A control with no obligation/framework link at all is un-verifiable, so it must
    # also be rejected rather than silently trusted.
    rejected_unlinked = client.post(
        f"{PORTAL_BASE}/invitations?engagement_id={engagement['id']}",
        headers=org["org_headers"],
        json={
            "auditor_email": "control-unlinked@example.com",
            "scoped_control_ids": [c_unlinked["id"]],
            "expires_in_days": 30,
        },
    )
    assert rejected_unlinked.status_code == 422

    # A control resolving to the engagement's own in-scope framework is accepted.
    accepted = _create_invitation(
        client,
        org["org_headers"],
        engagement["id"],
        {
            "auditor_email": "control-inscope@example.com",
            "scoped_control_ids": [c_in["id"]],
            "expires_in_days": 30,
        },
    )
    portal_headers = {"Authorization": f"Bearer {accepted['plaintext_token']}"}
    controls = client.get(f"{PORTAL_BASE}/controls", headers=portal_headers)
    assert controls.status_code == 200
    ids = {row["id"] for row in controls.json()}
    assert ids == {c_in["id"]}


def test_a43_engagement_scope_shrink_revokes_portal_visibility_immediately(client, db_session):
    """Regression: framework-based (default) scoping snapshotted the engagement's
    scope_framework_ids only at invitation-creation time. If the engagement's own scope
    was later narrowed (e.g. a framework removed from the audit), a previously-issued
    invitation kept full visibility into the now-removed framework's controls/evidence/
    reports until it expired -- a scope-drift containment bug. Access must now be
    computed against the *live* engagement scope on every request."""
    org = bootstrap_org_user(client, email_prefix="a43-scope-drift")
    fw_in_scope, fw_other = _framework_ids(client, org["headers"])
    engagement = _create_engagement(client, org["org_headers"], fw_in_scope, org["user_id"])

    ob_in = _create_obligation(db_session, fw_in_scope, "A43-DRIFT-IN")
    c_in = _create_control(client, org["org_headers"], "Drift control")
    row_in = db_session.query(Control).filter_by(id=uuid.UUID(c_in["id"])).one()
    row_in.obligation_id = ob_in.id
    db_session.commit()

    # Real control<->obligation membership is tracked via ControlObligationMapping.
    activate = client.post(f"/api/v1/frameworks/{fw_in_scope}/activate", headers=org["org_headers"], json={})
    assert activate.status_code == 200
    map_in = client.post(
        f"/api/v1/controls/{c_in['id']}/obligations",
        headers=org["org_headers"],
        json={"obligation_id": str(ob_in.id), "mapping_type": "satisfies"},
    )
    assert map_in.status_code == 200

    invitation = _create_invitation(
        client,
        org["org_headers"],
        engagement["id"],
        {"auditor_email": "drift-auditor@example.com", "expires_in_days": 30},
    )
    portal_headers = {"Authorization": f"Bearer {invitation['plaintext_token']}"}

    before = client.get(f"{PORTAL_BASE}/controls", headers=portal_headers)
    assert before.status_code == 200
    assert {row["id"] for row in before.json()} == {c_in["id"]}

    me_before = client.get(f"{PORTAL_BASE}/me", headers=portal_headers)
    assert me_before.status_code == 200
    assert me_before.json()["scope_changed_since_invitation"] is False

    # Shrink the engagement's own scope to remove fw_in_scope entirely.
    patch_resp = client.patch(
        f"{ENGAGEMENT_BASE}/{engagement['id']}",
        headers=org["org_headers"],
        json={"scope_framework_ids": [fw_other]},
    )
    assert patch_resp.status_code == 200

    after = client.get(f"{PORTAL_BASE}/controls", headers=portal_headers)
    assert after.status_code == 200
    assert after.json() == []

    me_after = client.get(f"{PORTAL_BASE}/me", headers=portal_headers)
    assert me_after.status_code == 200
    body = me_after.json()
    assert body["scope_changed_since_invitation"] is True
    assert body["effective_framework_ids"] == []
    assert body["scoped_framework_ids"] == [fw_in_scope]


def test_a44_finding_surfaces_control_context_and_scope_drift(client, db_session):
    """Regression: an audit finding only ever exposed a bare control_id, with no
    indication of which control failed, its current status, or whether the audit's
    scope had drifted since the finding was raised. Findings must now surface
    control_name/control_status/control_archived and scope_changed_since_creation."""
    org = bootstrap_org_user(client, email_prefix="a44-context")
    fw1, fw2 = _framework_ids(client, org["headers"])
    engagement = _create_engagement(client, org["org_headers"], fw1, org["user_id"])

    control = _create_control(client, org["org_headers"], "Failing control")
    finding = _create_finding(client, org["org_headers"], engagement["id"], org["user_id"], control_id=control["id"])
    assert finding["control_name"] == "Failing control"
    assert finding["control_status"] == "not_started"
    assert finding["control_archived"] is False
    assert finding["scope_changed_since_creation"] is False

    # Archive the linked control after the finding was raised.
    archived = client.patch(
        f"/api/v1/controls/{control['id']}",
        headers=org["org_headers"],
        json={"status": "archived"},
    )
    assert archived.status_code == 200

    # Narrow the engagement's own scope after the finding was raised.
    patch_resp = client.patch(
        f"{ENGAGEMENT_BASE}/{engagement['id']}",
        headers=org["org_headers"],
        json={"scope_framework_ids": [fw2]},
    )
    assert patch_resp.status_code == 200

    listed = client.get(f"{FINDINGS_BASE}", headers=org["org_headers"], params={"engagement_id": engagement["id"]})
    assert listed.status_code == 200
    listed_finding = next(row for row in listed.json() if row["id"] == finding["id"])
    assert listed_finding["control_status"] == "archived"
    assert listed_finding["control_archived"] is True
    assert listed_finding["scope_changed_since_creation"] is True


def test_a44_finding_context_only_shows_current_engagement_controls(client, db_session):
    """Context fields (control_name, control_status, control_archived) and scope-drift
    flags must be resolved only for controls linked to findings in the current
    engagement. Listing findings for one engagement must not surface control data from
    a sibling engagement or from a framework outside the current engagement's scope."""
    org = bootstrap_org_user(client, email_prefix="a44-context-scope")
    fw1, fw2 = _framework_ids(client, org["headers"])

    ob1 = _create_obligation(db_session, fw1, "A44-CTX-1")
    ob2 = _create_obligation(db_session, fw2, "A44-CTX-2")

    c1 = _create_control(client, org["org_headers"], "Engagement-1 control")
    c2 = _create_control(client, org["org_headers"], "Engagement-2 control")

    row_c1 = db_session.query(Control).filter_by(id=uuid.UUID(c1["id"])).one()
    row_c2 = db_session.query(Control).filter_by(id=uuid.UUID(c2["id"])).one()
    row_c1.obligation_id = ob1.id
    row_c2.obligation_id = ob2.id
    db_session.commit()

    engagement1 = _create_engagement(client, org["org_headers"], fw1, org["user_id"], title="Context A")
    engagement2 = _create_engagement(client, org["org_headers"], fw2, org["user_id"], title="Context B")

    finding1 = _create_finding(
        client,
        org["org_headers"],
        engagement1["id"],
        org["user_id"],
        title="Finding in engagement 1",
        control_id=c1["id"],
    )
    finding2 = _create_finding(
        client,
        org["org_headers"],
        engagement2["id"],
        org["user_id"],
        title="Finding in engagement 2",
        control_id=c2["id"],
    )

    listed = client.get(f"{FINDINGS_BASE}", headers=org["org_headers"], params={"engagement_id": engagement1["id"]})
    assert listed.status_code == 200
    items = listed.json()
    assert len(items) == 1
    assert items[0]["id"] == finding1["id"]
    assert items[0]["control_id"] == c1["id"]
    assert items[0]["control_name"] == "Engagement-1 control"
    assert items[0]["control_status"] == "not_started"
    assert items[0]["control_archived"] is False
    assert items[0]["scope_changed_since_creation"] is False
    assert all(row["control_id"] != c2["id"] for row in items)

    detail = client.get(f"{FINDINGS_BASE}/{finding1['id']}", headers=org["org_headers"])
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["control_name"] == "Engagement-1 control"
    assert payload["control_id"] != c2["id"]

    # Narrowing the engagement scope proves the scope-drift flag flips without
    # exposing the sibling engagement's control information.
    patch = client.patch(
        f"{ENGAGEMENT_BASE}/{engagement1['id']}",
        headers=org["org_headers"],
        json={"scope_framework_ids": [fw2]},
    )
    assert patch.status_code == 200

    listed_after = client.get(
        f"{FINDINGS_BASE}",
        headers=org["org_headers"],
        params={"engagement_id": engagement1["id"]},
    )
    assert listed_after.status_code == 200
    item_after = next(row for row in listed_after.json() if row["id"] == finding1["id"])
    assert item_after["scope_changed_since_creation"] is True
    assert item_after["control_name"] == "Engagement-1 control"

    _ = finding2


def test_a43_explicit_broad_scope_then_narrow_revokes_access(client, db_session):
    """Regression: an invitation explicitly granted broad visibility across multiple
    engagement frameworks must lose visibility into any framework that is later removed
    from the engagement's live scope, not just block new invitations."""
    org = bootstrap_org_user(client, email_prefix="a43-broad-narrow")
    fw1, fw2 = _framework_ids(client, org["headers"])

    engagement = _create_engagement(client, org["org_headers"], fw1, org["user_id"])
    # Start with both frameworks in scope.
    patch_resp = client.patch(
        f"{ENGAGEMENT_BASE}/{engagement['id']}",
        headers=org["org_headers"],
        json={"scope_framework_ids": [fw1, fw2]},
    )
    assert patch_resp.status_code == 200

    ob1 = _create_obligation(db_session, fw1, "A43-BROAD-1")
    ob2 = _create_obligation(db_session, fw2, "A43-BROAD-2")
    c1 = _create_control(client, org["org_headers"], "Broad control 1")
    c2 = _create_control(client, org["org_headers"], "Broad control 2")
    row_c1 = db_session.query(Control).filter_by(id=uuid.UUID(c1["id"])).one()
    row_c2 = db_session.query(Control).filter_by(id=uuid.UUID(c2["id"])).one()
    row_c1.obligation_id = ob1.id
    row_c2.obligation_id = ob2.id
    db_session.commit()

    # Real control<->obligation membership is tracked via ControlObligationMapping.
    for fw_id in (fw1, fw2):
        activate = client.post(f"/api/v1/frameworks/{fw_id}/activate", headers=org["org_headers"], json={})
        assert activate.status_code == 200
    map1 = client.post(
        f"/api/v1/controls/{c1['id']}/obligations",
        headers=org["org_headers"],
        json={"obligation_id": str(ob1.id), "mapping_type": "satisfies"},
    )
    assert map1.status_code == 200
    map2 = client.post(
        f"/api/v1/controls/{c2['id']}/obligations",
        headers=org["org_headers"],
        json={"obligation_id": str(ob2.id), "mapping_type": "satisfies"},
    )
    assert map2.status_code == 200

    invitation = _create_invitation(
        client,
        org["org_headers"],
        engagement["id"],
        {"auditor_email": "broad-auditor@example.com", "scoped_framework_ids": [fw1, fw2], "expires_in_days": 30},
    )
    portal_headers = {"Authorization": f"Bearer {invitation['plaintext_token']}"}

    before = client.get(f"{PORTAL_BASE}/controls", headers=portal_headers)
    assert before.status_code == 200
    assert {row["id"] for row in before.json()} == {c1["id"], c2["id"]}

    # Remove fw1 from the engagement's live scope.
    narrow = client.patch(
        f"{ENGAGEMENT_BASE}/{engagement['id']}",
        headers=org["org_headers"],
        json={"scope_framework_ids": [fw2]},
    )
    assert narrow.status_code == 200

    after = client.get(f"{PORTAL_BASE}/controls", headers=portal_headers)
    assert after.status_code == 200
    assert {row["id"] for row in after.json()} == {c2["id"]}

    me_after = client.get(f"{PORTAL_BASE}/me", headers=portal_headers)
    assert me_after.status_code == 200
    assert me_after.json()["effective_framework_ids"] == [fw2]
    assert me_after.json()["scope_changed_since_invitation"] is True


def test_a41_engagement_scope_impact_reports_stale_findings_and_packages(client):
    """Regression: nothing on the engagement itself told a reviewer how many findings or
    evidence packages were created before a scope change and are now stale -- they had
    to check each child record one at a time. GET .../scope-impact must report the blast
    radius of a scope change in one place."""
    org = bootstrap_org_user(client, email_prefix="a41-scope-impact")
    fw1, fw2 = _framework_ids(client, org["headers"])
    engagement = _create_engagement(client, org["org_headers"], fw1, org["user_id"])

    finding_before = _create_finding(client, org["org_headers"], engagement["id"], org["user_id"])

    pkg_resp = client.post(
        f"/api/v1/compliance/evidence-packages?engagement_id={engagement['id']}",
        headers=org["org_headers"],
        json={"title": "Pre-scope-change package", "scope_framework_ids": [fw1]},
    )
    assert pkg_resp.status_code == 201

    before = client.get(f"{ENGAGEMENT_BASE}/{engagement['id']}/scope-impact", headers=org["org_headers"])
    assert before.status_code == 200
    before_body = before.json()
    assert before_body["findings_total"] == 1
    assert before_body["findings_created_under_stale_scope"] == 0
    assert before_body["evidence_packages_total"] == 1
    assert before_body["evidence_packages_created_under_stale_scope"] == 0

    patch_resp = client.patch(
        f"{ENGAGEMENT_BASE}/{engagement['id']}",
        headers=org["org_headers"],
        json={"scope_framework_ids": [fw2]},
    )
    assert patch_resp.status_code == 200

    finding_after = _create_finding(client, org["org_headers"], engagement["id"], org["user_id"])

    after = client.get(f"{ENGAGEMENT_BASE}/{engagement['id']}/scope-impact", headers=org["org_headers"])
    assert after.status_code == 200
    after_body = after.json()
    assert after_body["findings_total"] == 2
    assert after_body["findings_created_under_stale_scope"] == 1
    assert after_body["evidence_packages_total"] == 1
    assert after_body["evidence_packages_created_under_stale_scope"] == 1
    assert after_body["current_scope_framework_ids"] == [fw2]

    _ = finding_before, finding_after


def test_g4_v2_resolve_status_does_not_crash_v1_list_and_is_transitionable(client):
    """Regression: the v2/pbc surface (POST .../audits/{id}/findings + .../resolve) writes
    AuditFinding.status="resolved" onto the SAME audit_findings table the v1 surface reads.
    AuditFindingRead (used only by v1's GET /compliance/audit-findings and GET /{id})
    validates status against FINDING_STATUS_PATTERN. Before this fix, "resolved" (and
    "remediation_in_progress") were not in that pattern, so serializing ANY finding in the
    org -- not just the resolved one -- raised a pydantic ValidationError and 500'd the
    whole v1 list/detail endpoints for every user in the org. Additionally, the v1
    /transition endpoint's ALLOWED_TRANSITIONS state machine didn't recognize "resolved"
    as a source state at all, so a resolved finding was permanently stuck and could only
    be closed via the side-door /close endpoint (which bypasses this state machine and
    the status pattern entirely)."""
    org = bootstrap_org_user(client, email_prefix="g4-cross-surface")
    fw1, _ = _framework_ids(client, org["headers"])
    engagement = _create_engagement(client, org["org_headers"], fw1, org["user_id"], title="G4 Cross Surface")

    # Create via the v2/pbc surface and resolve it there.
    v2_created = client.post(
        f"/api/v1/compliance/audits/{engagement['id']}/findings",
        headers=org["org_headers"],
        json={
            "title": "V2 finding to resolve",
            "description": "desc",
            "severity": "high",
            "finding_type": "observation",
            "remediation_plan": "Do X",
            "remediation_due_date": (date.today() + timedelta(days=10)).isoformat(),
        },
    )
    assert v2_created.status_code == 201
    finding_id = v2_created.json()["id"]

    resolved = client.post(f"/api/v1/compliance/audit-findings/{finding_id}/resolve", headers=org["org_headers"], json={})
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"

    # The v1 list and detail endpoints must not 500 just because a resolved finding
    # exists in the org, regardless of which surface wrote it.
    listed = client.get(FINDINGS_BASE, headers=org["org_headers"])
    assert listed.status_code == 200
    listed_row = next(row for row in listed.json() if row["id"] == finding_id)
    assert listed_row["status"] == "resolved"

    detail = client.get(f"{FINDINGS_BASE}/{finding_id}", headers=org["org_headers"])
    assert detail.status_code == 200
    assert detail.json()["status"] == "resolved"

    # A resolved finding must be transitionable through the SAME standard endpoint every
    # other finding uses -- both onward to closed and back to in_remediation if reopened
    # -- without needing the side-door /close endpoint.
    closed = client.post(
        f"{FINDINGS_BASE}/{finding_id}/transition",
        headers=org["org_headers"],
        json={"new_status": "closed"},
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert closed.json()["closed_at"] is not None
    assert closed.json()["closed_by"] == org["user_id"]

    # Second finding: resolve then reopen to in_remediation instead of closing.
    v2_created_2 = client.post(
        f"/api/v1/compliance/audits/{engagement['id']}/findings",
        headers=org["org_headers"],
        json={
            "title": "V2 finding to reopen",
            "description": "desc",
            "severity": "medium",
            "finding_type": "observation",
            "remediation_plan": "Do Y",
            "remediation_due_date": (date.today() + timedelta(days=10)).isoformat(),
        },
    )
    finding_id_2 = v2_created_2.json()["id"]
    client.post(f"/api/v1/compliance/audit-findings/{finding_id_2}/resolve", headers=org["org_headers"], json={})

    reopened = client.post(
        f"{FINDINGS_BASE}/{finding_id_2}/transition",
        headers=org["org_headers"],
        json={"new_status": "in_remediation"},
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "in_remediation"

    # v2's remediation_in_progress status must also not crash the v1 list, and must be
    # escapable through the standard transition endpoint (same bug class).
    v2_created_3 = client.post(
        f"/api/v1/compliance/audits/{engagement['id']}/findings",
        headers=org["org_headers"],
        json={
            "title": "V2 finding remediation in progress",
            "description": "desc",
            "severity": "low",
            "finding_type": "observation",
            "remediation_plan": "Initial plan",
            "remediation_due_date": (date.today() + timedelta(days=10)).isoformat(),
        },
    )
    finding_id_3 = v2_created_3.json()["id"]
    remediation_update = client.patch(
        f"/api/v1/compliance/audit-findings/{finding_id_3}/remediation",
        headers=org["org_headers"],
        json={"remediation_plan": "Updated plan"},
    )
    assert remediation_update.status_code == 200
    assert remediation_update.json()["status"] == "remediation_in_progress"

    listed_after = client.get(FINDINGS_BASE, headers=org["org_headers"])
    assert listed_after.status_code == 200

    remediated = client.post(
        f"{FINDINGS_BASE}/{finding_id_3}/transition",
        headers=org["org_headers"],
        json={"new_status": "remediated"},
    )
    assert remediated.status_code == 200
    assert remediated.json()["status"] == "remediated"
