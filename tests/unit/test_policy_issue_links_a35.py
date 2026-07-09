import uuid

from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/compliance/policy-issue-links"


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


def _create_real_issue(client, headers: dict[str, str], *, title: str, owner_id: str) -> dict:
    """Create a real, Issue-model-backed issue via /compliance/issues.

    This is the actual issue-tracking feature; it is NOT backed by the legacy
    ``tasks`` table that the deprecated v1 policy-issue-links endpoints below
    resolve issue_id against (see app/api/v1/policy_issue_links.py).
    """
    response = client.post(
        "/api/v1/compliance/issues",
        headers=headers,
        json={
            "title": title,
            "description": "Issue context",
            "issue_type": "compliance_violation",
            "severity": "high",
            "owner_id": owner_id,
        },
    )
    assert response.status_code == 201
    return response.json()


def _link_via_v2(client, headers: dict[str, str], *, policy_id: str, issue_id: str):
    return client.post(
        f"/api/v1/compliance/policies/{policy_id}/issues",
        headers=headers,
        json={"issue_id": issue_id, "link_reason": "test"},
    )


def test_a35_v1_write_and_lookup_endpoints_are_deprecated(client):
    """The v1 policy-issue-links surface only ever resolved issue_id against the legacy
    Task-backed issue concept, so every endpoint that depends on that lookup returns a
    misleading "Issue not found" 404 for real issues (created via /compliance/issues).
    These endpoints are now cleanly deprecated (410 Gone) rather than left silently broken.
    """
    org = bootstrap_org_user(client, email_prefix="a35-deprecated")
    policy = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="A35 Policy")
    issue = _create_real_issue(client, org["org_headers"], title="A35 Issue", owner_id=org["user_id"])

    create_resp = client.post(
        BASE,
        headers=org["org_headers"],
        json={"policy_id": policy["id"], "issue_id": issue["id"], "violation_type": "violation", "severity_impact": "high"},
    )
    assert create_resp.status_code == 410

    some_id = str(uuid.uuid4())
    assert client.get(f"{BASE}/{some_id}", headers=org["org_headers"]).status_code == 410
    assert client.patch(f"{BASE}/{some_id}", headers=org["org_headers"], json={"notes": "x"}).status_code == 410
    assert client.delete(f"{BASE}/{some_id}", headers=org["org_headers"]).status_code == 410
    assert client.get(BASE, headers=org["org_headers"]).status_code == 410
    assert client.get(f"{BASE}/summary", headers=org["org_headers"]).status_code == 410
    assert client.get(f"/api/v1/compliance/policies/{policy['id']}/issue-links", headers=org["org_headers"]).status_code == 410
    assert client.get(f"/api/v1/compliance/policies/{policy['id']}/effectiveness", headers=org["org_headers"]).status_code == 410
    assert client.get(f"/api/v1/compliance/issues/{issue['id']}/policy-context", headers=org["org_headers"]).status_code == 410

    # The 410 body should steer callers at the working v2 replacement, not just say "gone".
    assert "compliance/policies/{policy_id}/issues" in create_resp.json()["detail"]


def test_a35_issue_policy_links_surface_still_works_for_real_issues(client):
    """GET /issues/{issue_id}/policy-links is the one v1-router endpoint that already falls
    back to the v2 (Issue-model-backed) data source, so it must keep working for real issues.
    """
    org = bootstrap_org_user(client, email_prefix="a35-surface")
    policy = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="Surface Policy")
    issue = _create_real_issue(client, org["org_headers"], title="Surface Issue", owner_id=org["user_id"])

    linked = _link_via_v2(client, org["org_headers"], policy_id=policy["id"], issue_id=issue["id"])
    assert linked.status_code == 201

    surface = client.get(f"/api/v1/compliance/issues/{issue['id']}/policy-links", headers=org["org_headers"])
    assert surface.status_code == 200
    rows = surface.json()
    assert len(rows) == 1
    assert rows[0]["policy_id"] == policy["id"]
    assert rows[0]["issue"]["id"] == issue["id"]
