import uuid

from app.core.security import get_password_hash
from app.models.audit_log import AuditLog
from app.models.membership import Membership
from app.models.policy_issue_link import PolicyIssueLink
from app.models.role import Role
from app.models.task import Task
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user, login_user, org_headers

BASE = "/api/v1/compliance/policy-issue-links"


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


def _create_issue(
    client,
    headers: dict[str, str],
    *,
    title: str,
    status: str = "open",
    priority: str = "normal",
) -> dict:
    response = client.post(
        "/api/v1/tasks",
        headers=headers,
        json={
            "title": title,
            "description": "Issue context",
            "priority": priority,
            "task_type": "general",
        },
    )
    assert response.status_code == 201
    row = response.json()
    if status != "open":
        patch = client.patch(
            f"/api/v1/tasks/{row['id']}",
            headers=headers,
            json={"status": status},
        )
        assert patch.status_code == 200
        row = patch.json()
    return row


def _create_link(
    client,
    headers: dict[str, str],
    *,
    policy_id: str,
    issue_id: str,
    violation_type: str = "violation",
    severity_impact: str = "medium",
    notes: str | None = None,
):
    body = {
        "policy_id": policy_id,
        "issue_id": issue_id,
        "violation_type": violation_type,
        "severity_impact": severity_impact,
    }
    if notes is not None:
        body["notes"] = notes
    return client.post(BASE, headers=headers, json=body)


def test_a35_link_lifecycle_audit_soft_delete_and_remap(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a35-life")
    policy = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="A35 Policy")
    issue = _create_issue(client, org["org_headers"], title="A35 Issue")

    created = _create_link(
        client,
        org["org_headers"],
        policy_id=policy["id"],
        issue_id=issue["id"],
        violation_type="violation",
        severity_impact="medium",
        notes="Initial linkage",
    )
    assert created.status_code == 201
    link_id = created.json()["id"]

    audit_log = (
        db_session.query(AuditLog)
        .filter(AuditLog.organization_id == uuid.UUID(org["organization_id"]))
        .filter(AuditLog.action == "policy_issue_link.created")
        .filter(AuditLog.entity_id == uuid.UUID(link_id))
        .one_or_none()
    )
    assert audit_log is not None

    duplicate = _create_link(client, org["org_headers"], policy_id=policy["id"], issue_id=issue["id"])
    assert duplicate.status_code == 409

    updated = client.patch(
        f"{BASE}/{link_id}",
        headers=org["org_headers"],
        json={"violation_type": "procedural_gap", "notes": "Updated"},
    )
    assert updated.status_code == 200
    assert updated.json()["violation_type"] == "procedural_gap"
    assert updated.json()["notes"] == "Updated"

    deleted = client.delete(f"{BASE}/{link_id}", headers=org["org_headers"])
    assert deleted.status_code == 200

    active_list = client.get(BASE, headers=org["org_headers"])
    assert active_list.status_code == 200
    assert active_list.json() == []

    row = db_session.query(PolicyIssueLink).filter(PolicyIssueLink.id == uuid.UUID(link_id)).one()
    assert row.deleted_at is not None

    remapped = _create_link(
        client,
        org["org_headers"],
        policy_id=policy["id"],
        issue_id=issue["id"],
        violation_type="near_miss",
    )
    assert remapped.status_code == 201


def test_a35_cross_org_and_tenant_isolation(client):
    org_a = bootstrap_org_user(client, email_prefix="a35-org-a")
    org_b = bootstrap_org_user(client, email_prefix="a35-org-b")

    policy_a = _create_policy(client, org_a["org_headers"], owner_user_id=org_a["user_id"], title="Policy A")
    issue_a = _create_issue(client, org_a["org_headers"], title="Issue A")
    policy_b = _create_policy(client, org_b["org_headers"], owner_user_id=org_b["user_id"], title="Policy B")
    issue_b = _create_issue(client, org_b["org_headers"], title="Issue B")

    cross_policy = _create_link(client, org_a["org_headers"], policy_id=policy_b["id"], issue_id=issue_a["id"])
    assert cross_policy.status_code in {403, 404}

    cross_issue = _create_link(client, org_a["org_headers"], policy_id=policy_a["id"], issue_id=issue_b["id"])
    assert cross_issue.status_code in {403, 404}

    created_b = _create_link(client, org_b["org_headers"], policy_id=policy_b["id"], issue_id=issue_b["id"])
    assert created_b.status_code == 201

    list_a = client.get(BASE, headers=org_a["org_headers"])
    assert list_a.status_code == 200
    assert list_a.json() == []

    get_a = client.get(f"{BASE}/{created_b.json()['id']}", headers=org_a["org_headers"])
    assert get_a.status_code == 404

    delete_a = client.delete(f"{BASE}/{created_b.json()['id']}", headers=org_a["org_headers"])
    assert delete_a.status_code == 404


def test_a35_list_filters_policy_effectiveness_and_context(client):
    org = bootstrap_org_user(client, email_prefix="a35-coverage")
    policy1 = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="Policy 1")
    policy2 = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="Policy 2")

    issue1 = _create_issue(client, org["org_headers"], title="Issue 1", status="open", priority="urgent")
    issue2 = _create_issue(client, org["org_headers"], title="Issue 2", status="in_progress", priority="high")
    issue3 = _create_issue(client, org["org_headers"], title="Issue 3", status="completed", priority="normal")
    issue4 = _create_issue(client, org["org_headers"], title="Issue 4", status="blocked", priority="low")

    _create_link(client, org["org_headers"], policy_id=policy1["id"], issue_id=issue1["id"], violation_type="violation", severity_impact="high")
    _create_link(client, org["org_headers"], policy_id=policy1["id"], issue_id=issue2["id"], violation_type="violation", severity_impact="medium")
    _create_link(client, org["org_headers"], policy_id=policy1["id"], issue_id=issue3["id"], violation_type="near_miss", severity_impact="low")
    _create_link(client, org["org_headers"], policy_id=policy1["id"], issue_id=issue4["id"], violation_type="observation", severity_impact="critical")
    _create_link(client, org["org_headers"], policy_id=policy2["id"], issue_id=issue1["id"], violation_type="procedural_gap", severity_impact="high")

    by_policy = client.get(BASE, headers=org["org_headers"], params={"policy_id": policy1["id"]})
    assert by_policy.status_code == 200
    assert len(by_policy.json()) == 4

    by_issue = client.get(BASE, headers=org["org_headers"], params={"issue_id": issue1["id"]})
    assert by_issue.status_code == 200
    assert len(by_issue.json()) == 2

    by_violation = client.get(BASE, headers=org["org_headers"], params={"violation_type": "near_miss"})
    assert by_violation.status_code == 200
    assert len(by_violation.json()) == 1

    by_severity = client.get(BASE, headers=org["org_headers"], params={"severity_impact": "critical"})
    assert by_severity.status_code == 200
    assert len(by_severity.json()) == 1

    effectiveness = client.get(f"/api/v1/compliance/policies/{policy1['id']}/effectiveness", headers=org["org_headers"])
    assert effectiveness.status_code == 200
    eff = effectiveness.json()
    assert eff["total_issues_linked"] == 4
    assert eff["open_issues"] == 3
    assert eff["resolved_issues"] == 1
    assert eff["by_violation_type"]["violation"] == 2
    assert eff["by_violation_type"]["near_miss"] == 1
    assert eff["effectiveness_score"] == 25.0
    assert eff["trend_last_30d"] == 4
    assert eff["trend_last_90d"] == 4

    context = client.get(f"/api/v1/compliance/issues/{issue1['id']}/policy-context", headers=org["org_headers"])
    assert context.status_code == 200
    ctx = context.json()
    assert ctx["total_policies_linked"] == 2
    assert ctx["most_severe_impact"] == "high"


def test_a35_org_summary_and_surface_endpoints(client):
    org = bootstrap_org_user(client, email_prefix="a35-summary")
    policy1 = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="Policy One")
    policy2 = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="Policy Two")
    _policy3 = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="Policy Three")

    issue1 = _create_issue(client, org["org_headers"], title="Issue One", status="open")
    issue2 = _create_issue(client, org["org_headers"], title="Issue Two", status="completed")
    issue3 = _create_issue(client, org["org_headers"], title="Issue Three", status="open")

    _create_link(client, org["org_headers"], policy_id=policy1["id"], issue_id=issue1["id"], violation_type="violation", severity_impact="high")
    _create_link(client, org["org_headers"], policy_id=policy1["id"], issue_id=issue2["id"], violation_type="near_miss", severity_impact="medium")
    _create_link(client, org["org_headers"], policy_id=policy2["id"], issue_id=issue3["id"], violation_type="observation", severity_impact="low")

    summary = client.get("/api/v1/compliance/policy-issue-links/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_links"] == 3
    assert body["policies_with_issues"] == 2
    assert body["policies_without_issues"] == 1
    assert body["violation_type_breakdown"]["violation"] == 1
    assert body["violation_type_breakdown"]["near_miss"] == 1
    assert body["violation_type_breakdown"]["observation"] == 1
    assert len(body["most_violated_policies"]) >= 1

    policy_surface = client.get(f"/api/v1/compliance/policies/{policy1['id']}/issue-links", headers=org["org_headers"])
    assert policy_surface.status_code == 200
    assert len(policy_surface.json()) == 2

    issue_surface = client.get(f"/api/v1/compliance/issues/{issue1['id']}/policy-links", headers=org["org_headers"])
    assert issue_surface.status_code == 200
    assert len(issue_surface.json()) == 1


def test_a35_rbac_forbidden_for_non_manager_write_operations(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a35-rbac")
    reviewer_user = _create_active_user_with_role(
        db_session,
        org_id=org["organization_id"],
        email="a35-reviewer@example.com",
        role_name="reviewer",
    )
    reviewer_headers = org_headers(login_user(client, reviewer_user.email), org["organization_id"])

    policy = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="RBAC Policy")
    issue = _create_issue(client, org["org_headers"], title="RBAC Issue")
    created = _create_link(client, org["org_headers"], policy_id=policy["id"], issue_id=issue["id"])
    assert created.status_code == 201

    another_issue = _create_issue(client, org["org_headers"], title="RBAC Issue 2")
    create_forbidden = _create_link(
        client,
        reviewer_headers,
        policy_id=policy["id"],
        issue_id=another_issue["id"],
        notes="x",
    )
    assert create_forbidden.status_code == 403

    update_forbidden = client.patch(
        f"{BASE}/{created.json()['id']}",
        headers=reviewer_headers,
        json={"notes": "Nope"},
    )
    assert update_forbidden.status_code == 403

    delete_forbidden = client.delete(f"{BASE}/{created.json()['id']}", headers=reviewer_headers)
    assert delete_forbidden.status_code == 403
