from tests.helpers.auth_org import (
    auth_headers,
    bootstrap_admin_org,
    bootstrap_governance_manifest,
    bootstrap_org_user,
    login_user,
    org_headers,
)


def test_auth_org_helper_bootstrap_returns_expected_context(client):
    bootstrapped = bootstrap_org_user(client, email_prefix="p416-user", organization_name="P416 Org1")

    assert bootstrapped["user_id"]
    assert bootstrapped["organization_id"]
    assert bootstrapped["access_token"]
    assert bootstrapped["email"].startswith("p416-user-")
    assert bootstrapped["headers"] == auth_headers(bootstrapped["access_token"])
    assert bootstrapped["org_headers"] == org_headers(bootstrapped["access_token"], bootstrapped["organization_id"])

    me = client.get("/api/v1/auth/me", headers=bootstrapped["headers"])
    assert me.status_code == 200
    assert me.json()["id"] == bootstrapped["user_id"]


def test_auth_org_helper_admin_and_manifest_bootstrap(client):
    admin = bootstrap_admin_org(client, email_prefix="p416-admin", organization_name="P416 Org2")
    logged_in_token = login_user(client, admin["email"])
    assert logged_in_token
    manifest = bootstrap_governance_manifest(client, admin["org_headers"])
    assert manifest["manifest_id"]
