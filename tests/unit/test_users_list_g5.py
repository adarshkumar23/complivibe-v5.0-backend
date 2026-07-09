from tests.helpers.auth_org import bootstrap_org_user, org_headers


def test_list_users_returns_real_org_users(client):
    ctx = bootstrap_org_user(client, email_prefix="usrslist")
    headers = ctx["org_headers"]

    response = client.get("/api/v1/users", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    row = body[0]
    assert row["email"] == ctx["email"]
    assert "full_name" in row
    assert "status" in row
    assert "is_active" in row
    assert "is_superuser" in row
    assert "detail" not in row


def test_list_users_matches_scim_membership_scope(client):
    ctx = bootstrap_org_user(client, email_prefix="usrslist2")
    headers = ctx["org_headers"]

    other_ctx = bootstrap_org_user(client, email_prefix="usrslistother")

    response = client.get("/api/v1/users", headers=headers)
    assert response.status_code == 200
    emails = {row["email"] for row in response.json()}
    assert ctx["email"] in emails
    assert other_ctx["email"] not in emails
