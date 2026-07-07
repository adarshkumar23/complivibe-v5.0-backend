import uuid
from datetime import UTC, datetime, timedelta

from app.core.security import get_password_hash
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User


def _register(client, email: str, password: str, org_name: str) -> str:
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "organization_name": org_name},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _login(client, email: str, password: str) -> str:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _headers(token: str, org_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organization-ID"] = org_id
    return headers


def _create_active_user_with_role(db_session, org_id: str, email: str, role_name: str) -> User:
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
    membership = Membership(
        organization_id=uuid.UUID(org_id),
        user_id=user.id,
        role_id=role.id,
        status="active",
    )
    db_session.add(membership)
    db_session.commit()
    return user


def _org_id(client, token: str) -> str:
    return client.get("/api/v1/organizations/me", headers=_headers(token)).json()[0]["id"]


def _create_control(client, token: str, org_id: str, title: str = "Evidence Control") -> str:
    resp = client.post(
        "/api/v1/controls",
        headers=_headers(token, org_id),
        json={"title": title, "control_type": "process", "criticality": "medium"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_evidence_create_permissions_and_tenant_scoping(client, db_session):
    owner1 = _register(client, "p22-owner1@example.com", "Pass1234!@", "P22 Org1")
    owner2 = _register(client, "p22-owner2@example.com", "Pass1234!@", "P22 Org2")
    org1 = _org_id(client, owner1)
    org2 = _org_id(client, owner2)

    cm_user = _create_active_user_with_role(db_session, org1, "p22-cm@example.com", "compliance_manager")
    readonly_user = _create_active_user_with_role(db_session, org1, "p22-readonly@example.com", "readonly")
    auditor_user = _create_active_user_with_role(db_session, org1, "p22-auditor@example.com", "auditor")

    cm_token = _login(client, cm_user.email, "Pass1234!@")
    readonly_token = _login(client, readonly_user.email, "Pass1234!@")
    auditor_token = _login(client, auditor_user.email, "Pass1234!@")

    payload = {
        "title": "Access Policy v1",
        "evidence_type": "policy_document",
        "file_name": "access-policy.pdf",
        "mime_type": "application/pdf",
    }

    owner_create = client.post("/api/v1/evidence", headers=_headers(owner1, org1), json=payload)
    assert owner_create.status_code == 201

    cm_create = client.post(
        "/api/v1/evidence",
        headers=_headers(cm_token, org1),
        json={**payload, "title": "CM Evidence"},
    )
    assert cm_create.status_code == 201

    ro_create = client.post("/api/v1/evidence", headers=_headers(readonly_token, org1), json=payload)
    assert ro_create.status_code == 403

    auditor_create = client.post("/api/v1/evidence", headers=_headers(auditor_token, org1), json=payload)
    assert auditor_create.status_code == 403

    org1_rows = client.get("/api/v1/evidence", headers=_headers(owner1, org1))
    org2_rows = client.get("/api/v1/evidence", headers=_headers(owner2, org2))
    assert org1_rows.status_code == 200
    assert org2_rows.status_code == 200
    assert len(org1_rows.json()) >= 2
    assert org2_rows.json() == []


def test_evidence_detail_update_archive_freshness_and_audit(client):
    owner = _register(client, "p22-owner3@example.com", "Pass1234!@", "P22 Org3")
    org_id = _org_id(client, owner)

    created = client.post(
        "/api/v1/evidence",
        headers=_headers(owner, org_id),
        json={
            "title": "Config Snapshot",
            "evidence_type": "configuration_snapshot",
            "valid_until": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
        },
    )
    assert created.status_code == 201
    evidence_id = created.json()["id"]
    assert created.json()["freshness_status"] == "expired"

    detail = client.get(f"/api/v1/evidence/{evidence_id}", headers=_headers(owner, org_id))
    assert detail.status_code == 200
    assert detail.json()["linked_controls"] == []

    updated = client.patch(
        f"/api/v1/evidence/{evidence_id}",
        headers=_headers(owner, org_id),
        json={"description": "updated", "status": "superseded"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "superseded"

    archived = client.patch(f"/api/v1/evidence/{evidence_id}/archive", headers=_headers(owner, org_id))
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    logs = client.get("/api/v1/audit-logs", headers=_headers(owner, org_id)).json()
    actions = [item["action"] for item in logs]
    assert "evidence.created" in actions
    assert "evidence.updated" in actions
    assert "evidence.archived" in actions


def test_evidence_link_unlink_control_endpoint_and_cross_tenant_protection(client):
    owner1 = _register(client, "p22-owner4@example.com", "Pass1234!@", "P22 Org4")
    owner2 = _register(client, "p22-owner5@example.com", "Pass1234!@", "P22 Org5")
    org1 = _org_id(client, owner1)
    org2 = _org_id(client, owner2)

    control_id = _create_control(client, owner1, org1, "Control A")
    other_org_control = _create_control(client, owner2, org2, "Control B")

    created = client.post(
        "/api/v1/evidence",
        headers=_headers(owner1, org1),
        json={"title": "Audit Report", "evidence_type": "audit_report"},
    )
    evidence_id = created.json()["id"]

    linked = client.post(
        f"/api/v1/evidence/{evidence_id}/controls",
        headers=_headers(owner1, org1),
        json={"control_id": control_id, "confidence": "manual_confirmed"},
    )
    assert linked.status_code == 200
    assert linked.json()["link_status"] == "active"

    duplicate = client.post(
        f"/api/v1/evidence/{evidence_id}/controls",
        headers=_headers(owner1, org1),
        json={"control_id": control_id, "confidence": "manual_confirmed"},
    )
    assert duplicate.status_code == 200

    control_evidence = client.get(f"/api/v1/controls/{control_id}/evidence", headers=_headers(owner1, org1))
    assert control_evidence.status_code == 200
    assert any(item["id"] == evidence_id for item in control_evidence.json())

    cross_tenant_link = client.post(
        f"/api/v1/evidence/{evidence_id}/controls",
        headers=_headers(owner2, org2),
        json={"control_id": other_org_control},
    )
    assert cross_tenant_link.status_code == 404

    unlinked = client.delete(
        f"/api/v1/evidence/{evidence_id}/controls/{control_id}",
        headers=_headers(owner1, org1),
    )
    assert unlinked.status_code == 200
    assert unlinked.json()["link_status"] == "inactive"

    logs = client.get("/api/v1/audit-logs", headers=_headers(owner1, org1)).json()
    actions = [item["action"] for item in logs]
    assert "evidence.control_linked" in actions
    assert "evidence.control_unlinked" in actions


def test_evidence_review_and_readiness_summary(client):
    owner = _register(client, "p22-owner6@example.com", "Pass1234!@", "P22 Org6")
    org_id = _org_id(client, owner)

    control_verified = _create_control(client, owner, org_id, "Verified Control")
    control_empty = _create_control(client, owner, org_id, "No Evidence Control")

    evidence_verified = client.post(
        "/api/v1/evidence",
        headers=_headers(owner, org_id),
        json={"title": "Verified Evidence", "evidence_type": "attestation"},
    ).json()["id"]

    evidence_rejected = client.post(
        "/api/v1/evidence",
        headers=_headers(owner, org_id),
        json={
            "title": "Rejected Evidence",
            "evidence_type": "system_export",
            "valid_until": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        },
    ).json()["id"]

    link_resp = client.post(
        f"/api/v1/evidence/{evidence_verified}/controls",
        headers=_headers(owner, org_id),
        json={"control_id": control_verified},
    )
    assert link_resp.status_code == 200

    reject_without_notes = client.post(
        f"/api/v1/evidence/{evidence_rejected}/review",
        headers=_headers(owner, org_id),
        json={"review_status": "rejected"},
    )
    assert reject_without_notes.status_code == 400

    reviewed_verified = client.post(
        f"/api/v1/evidence/{evidence_verified}/review",
        headers=_headers(owner, org_id),
        json={"review_status": "verified", "review_notes": "Looks good"},
    )
    assert reviewed_verified.status_code == 200
    assert reviewed_verified.json()["review_status"] == "verified"

    reviewed_rejected = client.post(
        f"/api/v1/evidence/{evidence_rejected}/review",
        headers=_headers(owner, org_id),
        json={"review_status": "rejected", "review_notes": "Insufficient evidence"},
    )
    assert reviewed_rejected.status_code == 200

    summary = client.get("/api/v1/evidence/readiness/summary", headers=_headers(owner, org_id))
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_evidence_items"] >= 2
    assert body["verified_evidence_items"] >= 1
    assert body["rejected_evidence_items"] >= 1
    assert body["expired_evidence_items"] >= 1
    assert body["controls_with_verified_evidence"] >= 1
    assert body["controls_without_evidence"] >= 1  # includes control_empty

    logs = client.get("/api/v1/audit-logs", headers=_headers(owner, org_id)).json()
    assert "evidence.reviewed" in [item["action"] for item in logs]


def test_evidence_readiness_gaps_reports_specific_controls_and_reasons(client):
    """Regression: readiness/summary only ever reported a bare
    controls_without_evidence count. This endpoint must instead name exactly which
    controls are gaps and why: never linked to any evidence, linked but the evidence
    was rejected, linked but the evidence has since expired, or linked but still
    awaiting review -- and it must paginate rather than dumping every control."""
    owner = _register(client, "p22-gaps-owner@example.com", "Pass1234!@", "P22 Gaps Org")
    org_id = _org_id(client, owner)

    control_never_linked = _create_control(client, owner, org_id, "Never linked control")
    control_rejected = _create_control(client, owner, org_id, "Rejected evidence control")
    control_expired = _create_control(client, owner, org_id, "Expired evidence control")
    control_unreviewed = _create_control(client, owner, org_id, "Unreviewed evidence control")
    control_verified = _create_control(client, owner, org_id, "Verified control")

    def _create_and_link(title: str, control_id: str, *, valid_until: str | None = None) -> str:
        payload = {"title": title, "evidence_type": "attestation"}
        if valid_until is not None:
            payload["valid_until"] = valid_until
        evidence_id = client.post("/api/v1/evidence", headers=_headers(owner, org_id), json=payload).json()["id"]
        link = client.post(
            f"/api/v1/evidence/{evidence_id}/controls",
            headers=_headers(owner, org_id),
            json={"control_id": control_id},
        )
        assert link.status_code == 200
        return evidence_id

    rejected_evidence = _create_and_link("Rejected evidence", control_rejected)
    client.post(
        f"/api/v1/evidence/{rejected_evidence}/review",
        headers=_headers(owner, org_id),
        json={"review_status": "rejected", "review_notes": "Not sufficient"},
    )

    _create_and_link(
        "Expired evidence",
        control_expired,
        valid_until=(datetime.now(UTC) - timedelta(days=1)).isoformat(),
    )

    _create_and_link("Unreviewed evidence", control_unreviewed)

    verified_evidence = _create_and_link("Verified evidence", control_verified)
    client.post(
        f"/api/v1/evidence/{verified_evidence}/review",
        headers=_headers(owner, org_id),
        json={"review_status": "verified", "review_notes": "Good"},
    )

    gaps = client.get("/api/v1/evidence/readiness/gaps", headers=_headers(owner, org_id))
    assert gaps.status_code == 200
    body = gaps.json()
    reasons_by_control = {row["control_name"]: row["reason"] for row in body["items"]}

    assert reasons_by_control["Never linked control"] == "never_linked"
    assert reasons_by_control["Rejected evidence control"] == "linked_but_rejected"
    assert reasons_by_control["Expired evidence control"] == "linked_but_expired"
    assert reasons_by_control["Unreviewed evidence control"] == "linked_but_not_reviewed"
    assert "Verified control" not in reasons_by_control
    assert body["total"] == 4

    paged = client.get(
        "/api/v1/evidence/readiness/gaps",
        headers=_headers(owner, org_id),
        params={"limit": 2, "offset": 0},
    )
    assert paged.status_code == 200
    paged_body = paged.json()
    assert paged_body["total"] == 4
    assert len(paged_body["items"]) == 2
