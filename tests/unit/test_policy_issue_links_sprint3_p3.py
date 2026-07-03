import uuid
from datetime import datetime, timedelta

from app.models.audit_log import AuditLog
from app.models.issue import Issue
from app.models.issue_policy_link import IssuePolicyLink
from tests.helpers.auth_org import bootstrap_org_user


def _create_policy(client, headers: dict[str, str], owner_user_id: str, title: str) -> dict:
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
            "content_url": "https://example.com/policy.txt",
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_issue(client, headers: dict[str, str], owner_user_id: str, title: str, issue_type: str = "policy_violation") -> dict:
    response = client.post(
        "/api/v1/compliance/issues",
        headers=headers,
        json={
            "title": title,
            "description": "Issue description",
            "issue_type": issue_type,
            "severity": "high",
            "source_type": "manual",
            "owner_id": owner_user_id,
            "assigned_to": owner_user_id,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_s3_p3_link_duplicate_unlink_list_and_cross_org(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="s3p3-a")
    org_b = bootstrap_org_user(client, email_prefix="s3p3-b")

    policy = _create_policy(client, org_a["org_headers"], org_a["user_id"], "Policy A")
    issue_1 = _create_issue(client, org_a["org_headers"], org_a["user_id"], "Issue One")
    issue_2 = _create_issue(client, org_a["org_headers"], org_a["user_id"], "Issue Two")
    issue_other = _create_issue(client, org_b["org_headers"], org_b["user_id"], "Issue Other Org")

    # (a) link an issue and assert listed under policy
    linked = client.post(
        f"/api/v1/compliance/policies/{policy['id']}/issues",
        headers=org_a["org_headers"],
        json={"issue_id": issue_1["id"], "link_reason": "violates clause 3"},
    )
    assert linked.status_code == 201
    linked_list = client.get(f"/api/v1/compliance/policies/{policy['id']}/issues", headers=org_a["org_headers"])
    assert linked_list.status_code == 200
    assert any(row["id"] == issue_1["id"] for row in linked_list.json())

    # (b) duplicate link -> 409
    duplicate = client.post(
        f"/api/v1/compliance/policies/{policy['id']}/issues",
        headers=org_a["org_headers"],
        json={"issue_id": issue_1["id"]},
    )
    assert duplicate.status_code == 409

    # add second link and assert reverse listing (d)
    linked_2 = client.post(
        f"/api/v1/compliance/policies/{policy['id']}/issues",
        headers=org_a["org_headers"],
        json={"issue_id": issue_2["id"]},
    )
    assert linked_2.status_code == 201
    issue_policies = client.get(f"/api/v1/compliance/issues/{issue_2['id']}/policies", headers=org_a["org_headers"])
    assert issue_policies.status_code == 200
    assert any(row["id"] == policy["id"] for row in issue_policies.json())

    # (e) include_resolved filter behavior
    for next_status in ["investigating", "mitigating", "resolved"]:
        transition = client.post(
            f"/api/v1/compliance/issues/{issue_2['id']}/transition",
            headers=org_a["org_headers"],
            json={"new_status": next_status},
        )
        assert transition.status_code == 200
    unresolved_only = client.get(
        f"/api/v1/compliance/policies/{policy['id']}/issues?include_resolved=false",
        headers=org_a["org_headers"],
    )
    assert unresolved_only.status_code == 200
    assert all(row["id"] != issue_2["id"] for row in unresolved_only.json())
    include_resolved = client.get(
        f"/api/v1/compliance/policies/{policy['id']}/issues?include_resolved=true",
        headers=org_a["org_headers"],
    )
    assert include_resolved.status_code == 200
    assert any(row["id"] == issue_2["id"] for row in include_resolved.json())

    # (h) cross-org guards
    cross_org_link = client.post(
        f"/api/v1/compliance/policies/{policy['id']}/issues",
        headers=org_a["org_headers"],
        json={"issue_id": issue_other["id"]},
    )
    assert cross_org_link.status_code == 404
    cross_org_rate = client.get(
        f"/api/v1/compliance/policies/{policy['id']}/violation-rate",
        headers=org_b["org_headers"],
    )
    assert cross_org_rate.status_code == 404

    # (c) unlink is soft and removed from active list
    unlinked = client.delete(
        f"/api/v1/compliance/policies/{policy['id']}/issues/{issue_1['id']}",
        headers=org_a["org_headers"],
    )
    assert unlinked.status_code == 204
    after_unlink = client.get(f"/api/v1/compliance/policies/{policy['id']}/issues", headers=org_a["org_headers"])
    assert after_unlink.status_code == 200
    assert all(row["id"] != issue_1["id"] for row in after_unlink.json())
    link_row = (
        db_session.query(IssuePolicyLink)
        .filter(
            IssuePolicyLink.organization_id == uuid.UUID(org_a["organization_id"]),
            IssuePolicyLink.policy_id == uuid.UUID(policy["id"]),
            IssuePolicyLink.issue_id == uuid.UUID(issue_1["id"]),
        )
        .one()
    )
    assert link_row.unlinked_at is not None
    assert link_row.unlinked_by is not None
    assert link_row.unlinked_by == uuid.UUID(org_a["user_id"])
    assert link_row.status == "inactive"

    # (i) audit logs exist
    actions = {
        row.action
        for row in db_session.query(AuditLog)
        .filter(AuditLog.organization_id == uuid.UUID(org_a["organization_id"]))
        .all()
    }
    assert "policy.issue_linked" in actions
    assert "policy.issue_unlinked" in actions


def test_s3_p3_violation_rate_and_trend(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s3p3-rate")
    policy = _create_policy(client, org["org_headers"], org["user_id"], "Policy Trend")

    i1 = _create_issue(client, org["org_headers"], org["user_id"], "Old One", issue_type="policy_violation")
    i2 = _create_issue(client, org["org_headers"], org["user_id"], "Old Two", issue_type="policy_violation")
    i3 = _create_issue(client, org["org_headers"], org["user_id"], "New One", issue_type="compliance_violation")
    i4 = _create_issue(client, org["org_headers"], org["user_id"], "New Two", issue_type="compliance_violation")
    i5 = _create_issue(client, org["org_headers"], org["user_id"], "New Three", issue_type="policy_violation")

    for issue in (i1, i2, i3, i4, i5):
        linked = client.post(
            f"/api/v1/compliance/policies/{policy['id']}/issues",
            headers=org["org_headers"],
            json={"issue_id": issue["id"]},
        )
        assert linked.status_code == 201

    # seed deterministic timestamps: first half has 2, second half has 3
    now = datetime.utcnow()
    issue_rows = {row.id: row for row in db_session.query(Issue).all()}
    issue_rows[uuid.UUID(i1["id"])].created_at = now - timedelta(days=280)
    issue_rows[uuid.UUID(i2["id"])].created_at = now - timedelta(days=220)
    issue_rows[uuid.UUID(i3["id"])].created_at = now - timedelta(days=110)
    issue_rows[uuid.UUID(i4["id"])].created_at = now - timedelta(days=60)
    issue_rows[uuid.UUID(i5["id"])].created_at = now - timedelta(days=10)
    db_session.commit()

    # (f) violation rate with known input
    rate = client.get(
        f"/api/v1/compliance/policies/{policy['id']}/violation-rate?lookback_days=300",
        headers=org["org_headers"],
    )
    assert rate.status_code == 200
    payload = rate.json()
    assert payload["total_linked_issues"] == 5
    assert payload["resolved_issues"] == 0
    assert payload["open_issues"] == 5
    assert payload["violation_rate_per_month"] == 0.5  # 5 / (300/30)
    assert payload["most_common_issue_type"] in {"policy_violation", "compliance_violation"}

    # (g) trend increasing + null threshold check
    assert payload["trend"] == "increasing"

    # decreasing trend: more issues in first half of lookback than second half
    policy_decreasing = _create_policy(client, org["org_headers"], org["user_id"], "Policy Decreasing")
    d1 = _create_issue(client, org["org_headers"], org["user_id"], "D1")
    d2 = _create_issue(client, org["org_headers"], org["user_id"], "D2")
    d3 = _create_issue(client, org["org_headers"], org["user_id"], "D3")
    d4 = _create_issue(client, org["org_headers"], org["user_id"], "D4")
    d5 = _create_issue(client, org["org_headers"], org["user_id"], "D5")
    for issue in (d1, d2, d3, d4, d5):
        linked = client.post(
            f"/api/v1/compliance/policies/{policy_decreasing['id']}/issues",
            headers=org["org_headers"],
            json={"issue_id": issue["id"]},
        )
        assert linked.status_code == 201
    issue_rows = {row.id: row for row in db_session.query(Issue).all()}
    issue_rows[uuid.UUID(d1["id"])].created_at = now - timedelta(days=290)
    issue_rows[uuid.UUID(d2["id"])].created_at = now - timedelta(days=250)
    issue_rows[uuid.UUID(d3["id"])].created_at = now - timedelta(days=230)
    issue_rows[uuid.UUID(d4["id"])].created_at = now - timedelta(days=200)
    issue_rows[uuid.UUID(d5["id"])].created_at = now - timedelta(days=20)
    db_session.commit()
    dec_rate = client.get(
        f"/api/v1/compliance/policies/{policy_decreasing['id']}/violation-rate?lookback_days=300",
        headers=org["org_headers"],
    )
    assert dec_rate.status_code == 200
    assert dec_rate.json()["trend"] == "decreasing"

    # stable trend: first/second half volumes within 20%
    policy_stable = _create_policy(client, org["org_headers"], org["user_id"], "Policy Stable")
    st1 = _create_issue(client, org["org_headers"], org["user_id"], "ST1")
    st2 = _create_issue(client, org["org_headers"], org["user_id"], "ST2")
    st3 = _create_issue(client, org["org_headers"], org["user_id"], "ST3")
    st4 = _create_issue(client, org["org_headers"], org["user_id"], "ST4")
    st5 = _create_issue(client, org["org_headers"], org["user_id"], "ST5")
    st6 = _create_issue(client, org["org_headers"], org["user_id"], "ST6")
    for issue in (st1, st2, st3, st4, st5, st6):
        linked = client.post(
            f"/api/v1/compliance/policies/{policy_stable['id']}/issues",
            headers=org["org_headers"],
            json={"issue_id": issue["id"]},
        )
        assert linked.status_code == 201
    issue_rows = {row.id: row for row in db_session.query(Issue).all()}
    issue_rows[uuid.UUID(st1["id"])].created_at = now - timedelta(days=280)
    issue_rows[uuid.UUID(st2["id"])].created_at = now - timedelta(days=240)
    issue_rows[uuid.UUID(st3["id"])].created_at = now - timedelta(days=200)
    issue_rows[uuid.UUID(st4["id"])].created_at = now - timedelta(days=120)
    issue_rows[uuid.UUID(st5["id"])].created_at = now - timedelta(days=60)
    issue_rows[uuid.UUID(st6["id"])].created_at = now - timedelta(days=10)
    db_session.commit()
    stable_rate = client.get(
        f"/api/v1/compliance/policies/{policy_stable['id']}/violation-rate?lookback_days=300",
        headers=org["org_headers"],
    )
    assert stable_rate.status_code == 200
    assert stable_rate.json()["trend"] == "stable"

    # fewer than 3 issues => null trend
    policy_small = _create_policy(client, org["org_headers"], org["user_id"], "Policy Small")
    s1 = _create_issue(client, org["org_headers"], org["user_id"], "S1")
    s2 = _create_issue(client, org["org_headers"], org["user_id"], "S2")
    for issue in (s1, s2):
        linked = client.post(
            f"/api/v1/compliance/policies/{policy_small['id']}/issues",
            headers=org["org_headers"],
            json={"issue_id": issue["id"]},
        )
        assert linked.status_code == 201
    small_rate = client.get(
        f"/api/v1/compliance/policies/{policy_small['id']}/violation-rate?lookback_days=365",
        headers=org["org_headers"],
    )
    assert small_rate.status_code == 200
    assert small_rate.json()["trend"] is None
