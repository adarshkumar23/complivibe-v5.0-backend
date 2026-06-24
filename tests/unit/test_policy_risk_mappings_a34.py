from datetime import datetime, UTC
import uuid

from app.core.security import get_password_hash
from app.models.audit_log import AuditLog
from app.models.membership import Membership
from app.models.policy_risk_mapping import PolicyRiskMapping
from app.models.risk import Risk
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user, login_user, org_headers

BASE = "/api/v1/compliance/policy-risk-mappings"


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


def _create_policy(client, headers: dict[str, str], *, owner_user_id: str, title: str) -> dict:
    response = client.post(
        "/api/v1/compliance/policies",
        headers=headers,
        json={
            "title": title,
            "description": "Policy text",
            "policy_type": "access_control",
            "status": "draft",
            "owner_user_id": owner_user_id,
            "version": "1.0",
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_risk(client, headers: dict[str, str], *, title: str, likelihood: int = 3, impact: int = 3) -> dict:
    response = client.post(
        "/api/v1/risks",
        headers=headers,
        json={
            "title": title,
            "description": "Risk description",
            "category": "other",
            "likelihood": likelihood,
            "impact": impact,
            "treatment_strategy": "undecided",
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_mapping(client, headers: dict[str, str], *, policy_id: str, risk_id: str, strength: str = "partial", notes: str | None = None):
    body = {
        "policy_id": policy_id,
        "risk_id": risk_id,
        "mitigation_strength": strength,
    }
    if notes is not None:
        body["notes"] = notes
    return client.post(BASE, headers=headers, json=body)


def test_a34_mapping_lifecycle_audit_soft_delete_and_remap(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a34-life")
    policy = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="A34 Policy")
    risk = _create_risk(client, org["org_headers"], title="A34 Risk")

    created = _create_mapping(
        client,
        org["org_headers"],
        policy_id=policy["id"],
        risk_id=risk["id"],
        strength="partial",
        notes="Initial mapping",
    )
    assert created.status_code == 201
    mapping_id = created.json()["id"]

    audit_log = (
        db_session.query(AuditLog)
        .filter(AuditLog.organization_id == uuid.UUID(org["organization_id"]))
        .filter(AuditLog.action == "policy_risk_mapping.created")
        .filter(AuditLog.entity_id == uuid.UUID(mapping_id))
        .one_or_none()
    )
    assert audit_log is not None

    duplicate = _create_mapping(client, org["org_headers"], policy_id=policy["id"], risk_id=risk["id"])
    assert duplicate.status_code == 409

    updated = client.patch(
        f"{BASE}/{mapping_id}",
        headers=org["org_headers"],
        json={"mitigation_strength": "full", "notes": "Updated rationale"},
    )
    assert updated.status_code == 200
    assert updated.json()["mitigation_strength"] == "full"
    assert updated.json()["notes"] == "Updated rationale"

    deleted = client.delete(f"{BASE}/{mapping_id}", headers=org["org_headers"])
    assert deleted.status_code == 200

    active_list = client.get(BASE, headers=org["org_headers"])
    assert active_list.status_code == 200
    assert active_list.json() == []

    row = db_session.query(PolicyRiskMapping).filter(PolicyRiskMapping.id == uuid.UUID(mapping_id)).one()
    assert row.deleted_at is not None

    remapped = _create_mapping(
        client,
        org["org_headers"],
        policy_id=policy["id"],
        risk_id=risk["id"],
        strength="indirect",
    )
    assert remapped.status_code == 201


def test_a34_cross_org_and_tenant_isolation(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="a34-org-a")
    org_b = bootstrap_org_user(client, email_prefix="a34-org-b")

    policy_a = _create_policy(client, org_a["org_headers"], owner_user_id=org_a["user_id"], title="Policy A")
    risk_a = _create_risk(client, org_a["org_headers"], title="Risk A")
    policy_b = _create_policy(client, org_b["org_headers"], owner_user_id=org_b["user_id"], title="Policy B")
    risk_b = _create_risk(client, org_b["org_headers"], title="Risk B")

    cross_policy = _create_mapping(client, org_a["org_headers"], policy_id=policy_b["id"], risk_id=risk_a["id"])
    assert cross_policy.status_code in {403, 404}

    cross_risk = _create_mapping(client, org_a["org_headers"], policy_id=policy_a["id"], risk_id=risk_b["id"])
    assert cross_risk.status_code in {403, 404}

    created_b = _create_mapping(client, org_b["org_headers"], policy_id=policy_b["id"], risk_id=risk_b["id"])
    assert created_b.status_code == 201

    list_a = client.get(BASE, headers=org_a["org_headers"])
    assert list_a.status_code == 200
    assert list_a.json() == []

    get_a = client.get(f"{BASE}/{created_b.json()['id']}", headers=org_a["org_headers"])
    assert get_a.status_code == 404

    delete_a = client.delete(f"{BASE}/{created_b.json()['id']}", headers=org_a["org_headers"])
    assert delete_a.status_code == 404


def test_a34_list_filters_and_surface_endpoints(client):
    org = bootstrap_org_user(client, email_prefix="a34-filters")
    policy1 = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="Policy 1")
    policy2 = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="Policy 2")
    risk1 = _create_risk(client, org["org_headers"], title="Risk 1")
    risk2 = _create_risk(client, org["org_headers"], title="Risk 2")
    risk3 = _create_risk(client, org["org_headers"], title="Risk 3")

    _create_mapping(client, org["org_headers"], policy_id=policy1["id"], risk_id=risk1["id"], strength="full")
    _create_mapping(client, org["org_headers"], policy_id=policy1["id"], risk_id=risk2["id"], strength="partial")
    _create_mapping(client, org["org_headers"], policy_id=policy2["id"], risk_id=risk3["id"], strength="indirect")

    by_policy = client.get(BASE, headers=org["org_headers"], params={"policy_id": policy1["id"]})
    assert by_policy.status_code == 200
    assert len(by_policy.json()) == 2

    by_risk = client.get(BASE, headers=org["org_headers"], params={"risk_id": risk3["id"]})
    assert by_risk.status_code == 200
    assert len(by_risk.json()) == 1
    assert by_risk.json()[0]["risk_id"] == risk3["id"]

    by_strength = client.get(BASE, headers=org["org_headers"], params={"mitigation_strength": "full"})
    assert by_strength.status_code == 200
    assert len(by_strength.json()) == 1

    all_rows = client.get(BASE, headers=org["org_headers"])
    assert all_rows.status_code == 200
    assert len(all_rows.json()) == 3

    policy_surface = client.get(f"/api/v1/compliance/policies/{policy1['id']}/risk-mappings", headers=org["org_headers"])
    assert policy_surface.status_code == 200
    assert len(policy_surface.json()) == 2

    risk_surface = client.get(f"/api/v1/compliance/risks/{risk1['id']}/policy-mappings", headers=org["org_headers"])
    assert risk_surface.status_code == 200
    assert len(risk_surface.json()) == 1


def test_a34_policy_and_risk_coverage_endpoints(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a34-coverage")
    policy = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="Coverage Policy")
    policy2 = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="Coverage Policy 2")

    risk1 = _create_risk(client, org["org_headers"], title="Critical Risk")
    risk2 = _create_risk(client, org["org_headers"], title="High Risk")
    risk3 = _create_risk(client, org["org_headers"], title="Medium Risk")
    risk4 = _create_risk(client, org["org_headers"], title="Unmapped Risk")
    _ = risk4

    risk_rows = (
        db_session.query(Risk)
        .filter(Risk.id.in_([uuid.UUID(risk1["id"]), uuid.UUID(risk2["id"]), uuid.UUID(risk3["id"])]))
        .all()
    )
    severity_by_id = {
        uuid.UUID(risk1["id"]): "critical",
        uuid.UUID(risk2["id"]): "high",
        uuid.UUID(risk3["id"]): "medium",
    }
    for row in risk_rows:
        row.severity = severity_by_id[row.id]
    db_session.commit()

    _create_mapping(client, org["org_headers"], policy_id=policy["id"], risk_id=risk1["id"], strength="full")
    _create_mapping(client, org["org_headers"], policy_id=policy["id"], risk_id=risk2["id"], strength="partial")
    _create_mapping(client, org["org_headers"], policy_id=policy["id"], risk_id=risk3["id"], strength="partial")
    _create_mapping(client, org["org_headers"], policy_id=policy2["id"], risk_id=risk1["id"], strength="partial")

    policy_coverage = client.get(f"/api/v1/compliance/policies/{policy['id']}/risk-coverage", headers=org["org_headers"])
    assert policy_coverage.status_code == 200
    body = policy_coverage.json()
    assert body["total_risks_mapped"] == 3
    assert body["by_strength"] == {"full": 1, "partial": 2, "indirect": 0}
    assert body["risk_severity_breakdown"]["critical"] == 1
    assert body["risk_severity_breakdown"]["high"] == 1
    assert body["risk_severity_breakdown"]["medium"] == 1
    assert body["unmapped_risk_count"] == 1

    risk_coverage_full = client.get(f"/api/v1/compliance/risks/{risk1['id']}/policy-coverage", headers=org["org_headers"])
    assert risk_coverage_full.status_code == 200
    full_body = risk_coverage_full.json()
    assert full_body["has_full_coverage"] is True

    risk_coverage_partial = client.get(f"/api/v1/compliance/risks/{risk2['id']}/policy-coverage", headers=org["org_headers"])
    assert risk_coverage_partial.status_code == 200
    partial_body = risk_coverage_partial.json()
    assert partial_body["has_full_coverage"] is False
    assert partial_body["by_strength"]["partial"] == 1


def test_a34_org_summary_counts_and_uncovered(client):
    org = bootstrap_org_user(client, email_prefix="a34-summary")

    p1 = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="P1")
    p2 = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="P2")
    _ = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="P3")

    r1 = _create_risk(client, org["org_headers"], title="Risk 1")
    r2 = _create_risk(client, org["org_headers"], title="Risk 2")
    r3 = _create_risk(client, org["org_headers"], title="Risk 3")
    r4 = _create_risk(client, org["org_headers"], title="Risk 4")

    _create_mapping(client, org["org_headers"], policy_id=p1["id"], risk_id=r1["id"], strength="full")
    _create_mapping(client, org["org_headers"], policy_id=p1["id"], risk_id=r2["id"], strength="partial")
    _create_mapping(client, org["org_headers"], policy_id=p2["id"], risk_id=r3["id"], strength="indirect")

    summary = client.get(f"{BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    payload = summary.json()

    assert payload["policies_with_mappings"] == 2
    assert payload["policies_without_mappings"] == 1
    assert payload["risks_with_mappings"] == 3
    assert payload["risks_without_mappings"] == 1
    assert payload["coverage_rate"] == 75.0
    assert any(item["risk_id"] == r4["id"] for item in payload["uncovered_risks"])


def test_a34_non_manager_cannot_create_update_delete(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a34-rbac")
    reviewer = _create_active_user_with_role(db_session, org["organization_id"], "a34-rbac-r@example.com", role_name="reviewer")
    reviewer_headers = org_headers(login_user(client, reviewer.email), org["organization_id"])

    policy = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="RBAC Policy")
    risk = _create_risk(client, org["org_headers"], title="RBAC Risk")

    create_forbidden = _create_mapping(client, reviewer_headers, policy_id=policy["id"], risk_id=risk["id"])
    assert create_forbidden.status_code == 403

    created = _create_mapping(client, org["org_headers"], policy_id=policy["id"], risk_id=risk["id"])
    assert created.status_code == 201

    update_forbidden = client.patch(
        f"{BASE}/{created.json()['id']}",
        headers=reviewer_headers,
        json={"notes": "x"},
    )
    assert update_forbidden.status_code == 403

    delete_forbidden = client.delete(f"{BASE}/{created.json()['id']}", headers=reviewer_headers)
    assert delete_forbidden.status_code == 403
