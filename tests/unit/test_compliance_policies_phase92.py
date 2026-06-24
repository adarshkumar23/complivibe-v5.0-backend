import uuid

from app.core.security import get_password_hash
from app.models.compliance_policy_control_link import CompliancePolicyControlLink
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/compliance/policies"


def _create_user_with_role(db_session, *, org_id: str, email: str, role_name: str) -> User:
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


def _create_policy(client, headers: dict[str, str], *, owner_user_id: str, title: str = "Policy Link") -> dict:
    response = client.post(
        BASE,
        headers=headers,
        json={
            "title": title,
            "policy_type": "acceptable_use",
            "owner_user_id": owner_user_id,
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_control(client, headers: dict[str, str], *, title: str = "Control Link") -> dict:
    response = client.post(
        "/api/v1/controls",
        headers=headers,
        json={
            "title": title,
            "control_type": "policy",
            "criticality": "high",
        },
    )
    assert response.status_code == 201
    return response.json()


def _archive_policy(client, headers: dict[str, str], policy_id: str) -> None:
    r1 = client.patch(f"{BASE}/{policy_id}", headers=headers, json={"status": "under_review"})
    assert r1.status_code == 200
    r2 = client.patch(f"{BASE}/{policy_id}", headers=headers, json={"status": "approved"})
    assert r2.status_code == 200
    r3 = client.patch(f"{BASE}/{policy_id}", headers=headers, json={"status": "deprecated"})
    assert r3.status_code == 200
    r4 = client.post(f"{BASE}/{policy_id}/archive", headers=headers, json={"reason": "retired"})
    assert r4.status_code == 200


def test_phase92_link_creation_and_duplicate_blocking(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p92-dup")
    owner = _create_user_with_role(
        db_session,
        org_id=org["organization_id"],
        email="p92-dup-owner@example.com",
        role_name="admin",
    )

    policy = _create_policy(client, org["org_headers"], owner_user_id=str(owner.id))
    control = _create_control(client, org["org_headers"], title="Control A")

    linked = client.post(
        f"{BASE}/{policy['id']}/links/controls",
        headers=org["org_headers"],
        json={"control_id": control["id"], "link_reason": "maps policy to control"},
    )
    assert linked.status_code == 201
    assert linked.json()["status"] == "active"

    duplicate = client.post(
        f"{BASE}/{policy['id']}/links/controls",
        headers=org["org_headers"],
        json={"control_id": control["id"], "link_reason": "duplicate"},
    )
    assert duplicate.status_code == 400


def test_phase92_tenant_boundary_enforcement(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p92-tenant-a")
    org2 = bootstrap_org_user(client, email_prefix="p92-tenant-b")

    owner1 = _create_user_with_role(
        db_session,
        org_id=org1["organization_id"],
        email="p92-tenant-owner1@example.com",
        role_name="admin",
    )
    owner2 = _create_user_with_role(
        db_session,
        org_id=org2["organization_id"],
        email="p92-tenant-owner2@example.com",
        role_name="admin",
    )

    policy1 = _create_policy(client, org1["org_headers"], owner_user_id=str(owner1.id), title="Org1 Policy")
    control1 = _create_control(client, org1["org_headers"], title="Org1 Control")
    control2 = _create_control(client, org2["org_headers"], title="Org2 Control")
    _ = owner2

    cross_control = client.post(
        f"{BASE}/{policy1['id']}/links/controls",
        headers=org1["org_headers"],
        json={"control_id": control2["id"], "link_reason": "cross org should fail"},
    )
    assert cross_control.status_code == 404

    link = client.post(
        f"{BASE}/{policy1['id']}/links/controls",
        headers=org1["org_headers"],
        json={"control_id": control1["id"], "link_reason": "valid"},
    )
    assert link.status_code == 201

    cross_list = client.get(f"{BASE}/{policy1['id']}/links/controls", headers=org2["org_headers"])
    assert cross_list.status_code == 404


def test_phase92_archived_policy_blocks_new_links(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p92-arch")
    owner = _create_user_with_role(
        db_session,
        org_id=org["organization_id"],
        email="p92-arch-owner@example.com",
        role_name="admin",
    )

    policy = _create_policy(client, org["org_headers"], owner_user_id=str(owner.id), title="Archive Link Policy")
    control = _create_control(client, org["org_headers"], title="Control Archive")
    _archive_policy(client, org["org_headers"], policy["id"])

    blocked = client.post(
        f"{BASE}/{policy['id']}/links/controls",
        headers=org["org_headers"],
        json={"control_id": control["id"], "link_reason": "should block"},
    )
    assert blocked.status_code == 400


def test_phase92_unlink_non_destructive_and_include_unlinked(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p92-unlink")
    owner = _create_user_with_role(
        db_session,
        org_id=org["organization_id"],
        email="p92-unlink-owner@example.com",
        role_name="admin",
    )

    policy = _create_policy(client, org["org_headers"], owner_user_id=str(owner.id), title="Unlink Policy")
    control = _create_control(client, org["org_headers"], title="Control Unlink")

    link = client.post(
        f"{BASE}/{policy['id']}/links/controls",
        headers=org["org_headers"],
        json={"control_id": control["id"], "link_reason": "start"},
    )
    assert link.status_code == 201
    link_id = link.json()["id"]

    missing_reason = client.post(
        f"{BASE}/{policy['id']}/links/controls/{link_id}/unlink",
        headers=org["org_headers"],
        json={},
    )
    assert missing_reason.status_code == 422

    unlinked = client.post(
        f"{BASE}/{policy['id']}/links/controls/{link_id}/unlink",
        headers=org["org_headers"],
        json={"unlink_reason": "no longer applicable"},
    )
    assert unlinked.status_code == 200
    assert unlinked.json()["status"] == "unlinked"

    default_list = client.get(f"{BASE}/{policy['id']}/links/controls", headers=org["org_headers"])
    assert default_list.status_code == 200
    assert default_list.json() == []

    include_unlinked_list = client.get(
        f"{BASE}/{policy['id']}/links/controls?include_unlinked=true",
        headers=org["org_headers"],
    )
    assert include_unlinked_list.status_code == 200
    assert len(include_unlinked_list.json()) == 1
    assert include_unlinked_list.json()[0]["status"] == "unlinked"

    persisted = db_session.query(CompliancePolicyControlLink).filter(CompliancePolicyControlLink.id == uuid.UUID(link_id)).one()
    assert persisted is not None
    assert persisted.status == "unlinked"


def test_phase92_summary_counts_and_audit_events(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p92-summary")
    owner = _create_user_with_role(
        db_session,
        org_id=org["organization_id"],
        email="p92-summary-owner@example.com",
        role_name="admin",
    )

    policy = _create_policy(client, org["org_headers"], owner_user_id=str(owner.id), title="Summary Policy")
    control_a = _create_control(client, org["org_headers"], title="Control S1")
    control_b = _create_control(client, org["org_headers"], title="Control S2")

    link_a = client.post(
        f"{BASE}/{policy['id']}/links/controls",
        headers=org["org_headers"],
        json={"control_id": control_a["id"], "link_reason": "a"},
    )
    assert link_a.status_code == 201
    link_b = client.post(
        f"{BASE}/{policy['id']}/links/controls",
        headers=org["org_headers"],
        json={"control_id": control_b["id"], "link_reason": "b"},
    )
    assert link_b.status_code == 201

    unlink_b = client.post(
        f"{BASE}/{policy['id']}/links/controls/{link_b.json()['id']}/unlink",
        headers=org["org_headers"],
        json={"unlink_reason": "cleanup"},
    )
    assert unlink_b.status_code == 200

    summary = client.get(f"{BASE}/{policy['id']}/links/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    body = summary.json()
    assert body["active_control_links"] == 1
    assert body["unlinked_control_links"] == 1
    assert body["total_active_links"] == 1
    assert body["total_unlinked_links"] == 1

    logs = client.get("/api/v1/audit-logs", headers=org["org_headers"])
    assert logs.status_code == 200
    actions = [row["action"] for row in logs.json()]
    assert "compliance_policy.control_linked" in actions
    assert "compliance_policy.control_unlinked" in actions
