from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import uuid

from app.core.security import get_password_hash
from app.models.auditor_portal_invitation import AuditorPortalInvitation
from app.models.control import Control
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

    detail = client.get(f"{PORTAL_BASE}/invitations/{created['invitation_id']}", headers=org["org_headers"])
    assert detail.status_code == 200
    payload = detail.json()
    assert "plaintext_token" not in payload
    assert "token_hash" not in payload


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

    row_in = db_session.query(Control).filter_by(id=uuid.UUID(c_in["id"])).one()
    row_out = db_session.query(Control).filter_by(id=uuid.UUID(c_out["id"])).one()
    row_b = db_session.query(Control).filter_by(id=uuid.UUID(c_org_b["id"])).one()
    row_in.obligation_id = ob_in.id
    row_out.obligation_id = ob_out.id
    row_b.obligation_id = ob_in.id
    db_session.commit()

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
