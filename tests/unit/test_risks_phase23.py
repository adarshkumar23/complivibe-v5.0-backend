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


def _org_id(client, token: str) -> str:
    return client.get("/api/v1/organizations/me", headers=_headers(token)).json()[0]["id"]


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


def _create_control(client, token: str, org_id: str, title: str = "Risk Control") -> str:
    resp = client.post(
        "/api/v1/controls",
        headers=_headers(token, org_id),
        json={"title": title, "control_type": "process", "criticality": "medium"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_evidence(client, token: str, org_id: str, title: str = "Risk Evidence") -> str:
    resp = client.post(
        "/api/v1/evidence",
        headers=_headers(token, org_id),
        json={"title": title, "evidence_type": "attestation"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_risk_permissions_tenant_scoping_scoring_and_validation(client, db_session):
    owner1 = _register(client, "p23-owner1@example.com", "Pass1234!@", "P23 Org1")
    owner2 = _register(client, "p23-owner2@example.com", "Pass1234!@", "P23 Org2")
    org1 = _org_id(client, owner1)
    org2 = _org_id(client, owner2)

    admin_user = _create_active_user_with_role(db_session, org1, "p23-admin@example.com", "admin")
    cm_user = _create_active_user_with_role(db_session, org1, "p23-cm@example.com", "compliance_manager")
    readonly_user = _create_active_user_with_role(db_session, org1, "p23-readonly@example.com", "readonly")
    auditor_user = _create_active_user_with_role(db_session, org1, "p23-auditor@example.com", "auditor")

    admin_token = _login(client, admin_user.email, "Pass1234!@")
    cm_token = _login(client, cm_user.email, "Pass1234!@")
    readonly_token = _login(client, readonly_user.email, "Pass1234!@")
    auditor_token = _login(client, auditor_user.email, "Pass1234!@")

    payload = {
        "title": "Unauthorized data access risk",
        "category": "security",
        "likelihood": 5,
        "impact": 4,
        "treatment_strategy": "mitigate",
    }

    owner_create = client.post("/api/v1/risks", headers=_headers(owner1, org1), json=payload)
    assert owner_create.status_code == 201
    risk_id = owner_create.json()["id"]
    assert owner_create.json()["inherent_score"] == 20
    assert owner_create.json()["severity"] == "critical"

    admin_create = client.post(
        "/api/v1/risks",
        headers=_headers(admin_token, org1),
        json={**payload, "title": "Admin risk", "likelihood": 2, "impact": 2},
    )
    assert admin_create.status_code == 201

    cm_create = client.post(
        "/api/v1/risks",
        headers=_headers(cm_token, org1),
        json={**payload, "title": "CM risk", "likelihood": 3, "impact": 2},
    )
    assert cm_create.status_code == 201

    ro_create = client.post("/api/v1/risks", headers=_headers(readonly_token, org1), json=payload)
    assert ro_create.status_code == 403

    auditor_create = client.post("/api/v1/risks", headers=_headers(auditor_token, org1), json=payload)
    assert auditor_create.status_code == 403

    bad_score = client.post(
        "/api/v1/risks",
        headers=_headers(owner1, org1),
        json={"title": "Bad", "category": "other", "likelihood": 6, "impact": 2},
    )
    assert bad_score.status_code == 422

    list1 = client.get("/api/v1/risks", headers=_headers(owner1, org1))
    list2 = client.get("/api/v1/risks", headers=_headers(owner2, org2))
    assert list1.status_code == 200
    assert list2.status_code == 200
    assert any(item["id"] == risk_id for item in list1.json())
    assert list2.json() == []


def test_risk_create_update_exposes_and_validates_business_unit_id(client):
    owner1 = _register(client, "p23-bu-owner1@example.com", "Pass1234!@", "P23 BU Org1")
    owner2 = _register(client, "p23-bu-owner2@example.com", "Pass1234!@", "P23 BU Org2")
    org1 = _org_id(client, owner1)
    org2 = _org_id(client, owner2)

    bu1 = client.post(
        "/api/v1/compliance/business-units",
        headers=_headers(owner1, org1),
        json={"name": "Payments", "code": "PAY"},
    )
    assert bu1.status_code == 201
    bu1_id = bu1.json()["id"]

    bu2 = client.post(
        "/api/v1/compliance/business-units",
        headers=_headers(owner2, org2),
        json={"name": "Other", "code": "OTH"},
    )
    assert bu2.status_code == 201

    created = client.post(
        "/api/v1/risks",
        headers=_headers(owner1, org1),
        json={
            "title": "BU-linked risk",
            "category": "operational",
            "likelihood": 3,
            "impact": 4,
            "business_unit_id": bu1_id,
        },
    )
    assert created.status_code == 201
    risk_id = created.json()["id"]
    assert created.json()["business_unit_id"] == bu1_id

    fetched = client.get(f"/api/v1/risks/{risk_id}", headers=_headers(owner1, org1))
    assert fetched.status_code == 200
    assert fetched.json()["business_unit_id"] == bu1_id

    listed = client.get(f"/api/v1/risks?business_unit_id={bu1_id}", headers=_headers(owner1, org1))
    assert listed.status_code == 200
    assert any(row["id"] == risk_id and row["business_unit_id"] == bu1_id for row in listed.json())

    cross_org_update = client.patch(
        f"/api/v1/risks/{risk_id}",
        headers=_headers(owner1, org1),
        json={"business_unit_id": bu2.json()["id"]},
    )
    assert cross_org_update.status_code == 400
    assert "business_unit_id" in cross_org_update.json()["detail"]

    cleared = client.patch(
        f"/api/v1/risks/{risk_id}",
        headers=_headers(owner1, org1),
        json={"business_unit_id": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["business_unit_id"] is None


def test_risk_update_owner_validation_archive_accept_and_audit(client, db_session):
    owner1 = _register(client, "p23-owner3@example.com", "Pass1234!@", "P23 Org3")
    owner2 = _register(client, "p23-owner4@example.com", "Pass1234!@", "P23 Org4")
    org1 = _org_id(client, owner1)
    org2 = _org_id(client, owner2)

    same_org_user = _create_active_user_with_role(db_session, org1, "p23-same-owner@example.com", "admin")
    other_org_user = _create_active_user_with_role(db_session, org2, "p23-other-owner@example.com", "admin")

    created = client.post(
        "/api/v1/risks",
        headers=_headers(owner1, org1),
        json={"title": "Privacy disclosure", "category": "privacy", "likelihood": 2, "impact": 3},
    )
    assert created.status_code == 201
    risk_id = created.json()["id"]

    bad_owner_update = client.patch(
        f"/api/v1/risks/{risk_id}",
        headers=_headers(owner1, org1),
        json={"owner_user_id": str(other_org_user.id)},
    )
    assert bad_owner_update.status_code == 400

    updated = client.patch(
        f"/api/v1/risks/{risk_id}",
        headers=_headers(owner1, org1),
        json={
            "owner_user_id": str(same_org_user.id),
            "likelihood": 4,
            "impact": 4,
            "residual_likelihood": 2,
            "residual_impact": 2,
            "status": "in_treatment",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["inherent_score"] == 16
    assert updated.json()["severity"] == "high"
    assert updated.json()["residual_score"] == 4

    no_reason_accept = client.post(f"/api/v1/risks/{risk_id}/accept", headers=_headers(owner1, org1), json={})
    assert no_reason_accept.status_code == 422

    accepted = client.post(
        f"/api/v1/risks/{risk_id}/accept",
        headers=_headers(owner1, org1),
        json={"acceptance_reason": "Business decision", "review_due_at": (datetime.now(UTC) + timedelta(days=30)).isoformat()},
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"
    assert accepted.json()["treatment_strategy"] == "accept"
    assert accepted.json()["accepted_at"] is not None

    archived = client.patch(f"/api/v1/risks/{risk_id}/archive", headers=_headers(owner1, org1))
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    logs = client.get("/api/v1/audit-logs", headers=_headers(owner1, org1)).json()
    actions = [item["action"] for item in logs]
    assert "risk.updated" in actions
    assert "risk.accepted" in actions
    assert "risk.archived" in actions


def test_risk_control_and_evidence_linking_detail_and_cross_tenant_rules(client):
    owner1 = _register(client, "p23-owner5@example.com", "Pass1234!@", "P23 Org5")
    owner2 = _register(client, "p23-owner6@example.com", "Pass1234!@", "P23 Org6")
    org1 = _org_id(client, owner1)
    org2 = _org_id(client, owner2)

    risk = client.post(
        "/api/v1/risks",
        headers=_headers(owner1, org1),
        json={"title": "Model drift risk", "category": "ai_governance", "likelihood": 3, "impact": 4},
    )
    risk_id = risk.json()["id"]

    control1 = _create_control(client, owner1, org1, "Mitigation Control")
    evidence1 = _create_evidence(client, owner1, org1, "Mitigation Evidence")

    control2 = _create_control(client, owner2, org2, "Other Org Control")
    evidence2 = _create_evidence(client, owner2, org2, "Other Org Evidence")

    link_control = client.post(
        f"/api/v1/risks/{risk_id}/controls",
        headers=_headers(owner1, org1),
        json={"control_id": control1, "link_type": "mitigates"},
    )
    assert link_control.status_code == 200

    dup_control = client.post(
        f"/api/v1/risks/{risk_id}/controls",
        headers=_headers(owner1, org1),
        json={"control_id": control1, "link_type": "mitigates"},
    )
    assert dup_control.status_code == 200

    unlink_control = client.delete(f"/api/v1/risks/{risk_id}/controls/{control1}", headers=_headers(owner1, org1))
    assert unlink_control.status_code == 200
    assert unlink_control.json()["status"] == "inactive"

    relink_control = client.post(
        f"/api/v1/risks/{risk_id}/controls",
        headers=_headers(owner1, org1),
        json={"control_id": control1, "link_type": "detects"},
    )
    assert relink_control.status_code == 200
    assert relink_control.json()["status"] == "active"

    cross_control = client.post(
        f"/api/v1/risks/{risk_id}/controls",
        headers=_headers(owner1, org1),
        json={"control_id": control2, "link_type": "related"},
    )
    assert cross_control.status_code == 404

    link_evidence = client.post(
        f"/api/v1/risks/{risk_id}/evidence",
        headers=_headers(owner1, org1),
        json={"evidence_item_id": evidence1, "link_type": "supports_mitigation"},
    )
    assert link_evidence.status_code == 200

    dup_evidence = client.post(
        f"/api/v1/risks/{risk_id}/evidence",
        headers=_headers(owner1, org1),
        json={"evidence_item_id": evidence1, "link_type": "supports_mitigation"},
    )
    assert dup_evidence.status_code == 200

    unlink_evidence = client.delete(f"/api/v1/risks/{risk_id}/evidence/{evidence1}", headers=_headers(owner1, org1))
    assert unlink_evidence.status_code == 200
    assert unlink_evidence.json()["status"] == "inactive"

    relink_evidence = client.post(
        f"/api/v1/risks/{risk_id}/evidence",
        headers=_headers(owner1, org1),
        json={"evidence_item_id": evidence1, "link_type": "supports_assessment"},
    )
    assert relink_evidence.status_code == 200
    assert relink_evidence.json()["status"] == "active"

    cross_evidence = client.post(
        f"/api/v1/risks/{risk_id}/evidence",
        headers=_headers(owner1, org1),
        json={"evidence_item_id": evidence2, "link_type": "related"},
    )
    assert cross_evidence.status_code == 404

    detail = client.get(f"/api/v1/risks/{risk_id}", headers=_headers(owner1, org1))
    assert detail.status_code == 200
    assert detail.json()["inherent_score"] == 12
    assert len(detail.json()["linked_controls"]) >= 1
    assert len(detail.json()["linked_evidence"]) >= 1

    logs = client.get("/api/v1/audit-logs", headers=_headers(owner1, org1)).json()
    actions = [item["action"] for item in logs]
    assert "risk.control_linked" in actions
    assert "risk.control_unlinked" in actions
    assert "risk.evidence_linked" in actions
    assert "risk.evidence_unlinked" in actions


def test_direct_risk_control_link_unlink_recomputes_residual_immediately(client):
    owner = _register(client, "p23-residual-owner@example.com", "Pass1234!@", "P23 Residual Org")
    org_id = _org_id(client, owner)

    risk = client.post(
        "/api/v1/risks",
        headers=_headers(owner, org_id),
        json={"title": "Immediate residual risk", "category": "security", "likelihood": 5, "impact": 4},
    )
    assert risk.status_code == 201
    risk_id = risk.json()["id"]
    assert risk.json()["residual_score"] == 20

    control_id = _create_control(client, owner, org_id, "Implemented Critical Control")
    implemented = client.patch(
        f"/api/v1/controls/{control_id}",
        headers=_headers(owner, org_id),
        json={"status": "implemented", "criticality": "critical"},
    )
    assert implemented.status_code == 200

    linked = client.post(
        f"/api/v1/risks/{risk_id}/controls",
        headers=_headers(owner, org_id),
        json={"control_id": control_id, "link_type": "mitigates"},
    )
    assert linked.status_code == 200

    after_link = client.get(f"/api/v1/risks/{risk_id}", headers=_headers(owner, org_id))
    assert after_link.status_code == 200
    assert after_link.json()["residual_likelihood"] == 3
    assert after_link.json()["residual_score"] == 12

    unlinked = client.delete(f"/api/v1/risks/{risk_id}/controls/{control_id}", headers=_headers(owner, org_id))
    assert unlinked.status_code == 200

    after_unlink = client.get(f"/api/v1/risks/{risk_id}", headers=_headers(owner, org_id))
    assert after_unlink.status_code == 200
    assert after_unlink.json()["residual_likelihood"] == 5
    assert after_unlink.json()["residual_score"] == 20


def test_risk_summary_and_heatmap(client):
    owner = _register(client, "p23-owner7@example.com", "Pass1234!@", "P23 Org7")
    org_id = _org_id(client, owner)

    # high/critical open risk with overdue review and no control
    r1 = client.post(
        "/api/v1/risks",
        headers=_headers(owner, org_id),
        json={"title": "Critical risk", "category": "security", "likelihood": 5, "impact": 4},
    ).json()["id"]
    client.patch(
        f"/api/v1/risks/{r1}",
        headers=_headers(owner, org_id),
        json={"review_due_at": (datetime.now(UTC) - timedelta(days=1)).isoformat()},
    )

    # medium risk then accepted
    r2 = client.post(
        "/api/v1/risks",
        headers=_headers(owner, org_id),
        json={"title": "Accepted risk", "category": "operational", "likelihood": 3, "impact": 2},
    ).json()["id"]
    client.post(
        f"/api/v1/risks/{r2}/accept",
        headers=_headers(owner, org_id),
        json={"acceptance_reason": "accepted for now"},
    )

    # low risk, archived later
    r3 = client.post(
        "/api/v1/risks",
        headers=_headers(owner, org_id),
        json={"title": "Low risk", "category": "other", "likelihood": 1, "impact": 2},
    ).json()["id"]
    client.patch(f"/api/v1/risks/{r3}/archive", headers=_headers(owner, org_id))

    summary = client.get("/api/v1/risks/summary", headers=_headers(owner, org_id))
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_risks"] >= 3
    assert body["accepted_risks"] >= 1
    assert body["critical_risks"] >= 1
    assert body["medium_risks"] >= 1
    assert body["overdue_risk_reviews"] >= 1
    assert body["risks_without_owner"] >= 1

    heatmap = client.get("/api/v1/risks/heatmap", headers=_headers(owner, org_id))
    assert heatmap.status_code == 200
    matrix = heatmap.json()["matrix"]
    assert len(matrix) == 25
    cell_54 = next(c for c in matrix if c["likelihood"] == 5 and c["impact"] == 4)
    assert cell_54["count"] >= 1
    assert any(r["title"] == "Critical risk" for r in cell_54["risks"])
