from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import inspect, select

from app.compliance.services.offboarding_service import OffboardingService
from app.models.audit_log import AuditLog
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.scim_token import ScimToken
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user


def _create_scim_token(client, org_headers: dict[str, str], description: str, expires_at: str | None = None) -> dict:
    payload: dict = {"description": description}
    if expires_at is not None:
        payload["expires_at"] = expires_at
    response = client.post("/api/v1/scim-tokens", headers=org_headers, json=payload)
    assert response.status_code == 201
    return response.json()


def _scim_headers(raw_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {raw_token}"}


def _sample_scim_user(email: str) -> dict:
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "userName": email,
        "name": {"givenName": "Jane", "familyName": "Smith"},
        "active": True,
    }


def _enable_scim_feature(db_session, organization_id: str) -> None:
    org = db_session.get(Organization, UUID(organization_id))
    assert org is not None
    org.subscription_status = "active"
    org.subscription_plan = "enterprise"
    db_session.commit()


def test_scim_token_lifecycle_and_hash_storage(client, db_session):
    org = bootstrap_org_user(client, email_prefix="scim-token")
    _enable_scim_feature(db_session, org["organization_id"])
    tables = set(inspect(db_session.bind).get_table_names())
    assert "scim_tokens" in tables

    created_a = _create_scim_token(client, org["org_headers"], "Okta SCIM integration A")
    created_b = _create_scim_token(client, org["org_headers"], "Okta SCIM integration B")
    assert created_a["raw_token"] != created_b["raw_token"]

    row_a = db_session.get(ScimToken, UUID(created_a["id"]))
    row_b = db_session.get(ScimToken, UUID(created_b["id"]))
    assert row_a is not None
    assert row_b is not None

    expected_hash_a = hashlib.sha256(created_a["raw_token"].encode("utf-8")).hexdigest()
    expected_hash_b = hashlib.sha256(created_b["raw_token"].encode("utf-8")).hexdigest()
    assert row_a.token_hash == expected_hash_a
    assert row_b.token_hash == expected_hash_b
    assert row_a.token_hash != row_b.token_hash

    listed = client.get("/api/v1/scim-tokens", headers=org["org_headers"])
    assert listed.status_code == 200
    assert listed.json()
    assert "token_hash" not in listed.text
    assert "raw_token" not in listed.text

    deleted = client.delete(f"/api/v1/scim-tokens/{created_a['id']}", headers=org["org_headers"])
    assert deleted.status_code == 204
    db_row = db_session.get(ScimToken, UUID(created_a["id"]))
    assert db_row is not None
    assert db_row.deleted_at is not None
    assert db_row.is_active is False


def test_scim_discovery_endpoints_public(client):
    service_provider = client.get("/api/v1/scim/v2/ServiceProviderConfig")
    assert service_provider.status_code == 200
    assert service_provider.headers["content-type"].startswith("application/scim+json")
    body = service_provider.json()
    assert body["patch"]["supported"] is True

    schemas = client.get("/api/v1/scim/v2/Schemas")
    assert schemas.status_code == 200
    assert schemas.headers["content-type"].startswith("application/scim+json")


def test_scim_user_operations_and_offboarding_trigger(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="scim-users")
    _enable_scim_feature(db_session, org["organization_id"])
    token_payload = _create_scim_token(client, org["org_headers"], "Okta Provisioning")
    scim_headers = _scim_headers(token_payload["raw_token"])

    listed = client.get("/api/v1/scim/v2/Users", headers=scim_headers)
    assert listed.status_code == 200
    assert listed.json()["schemas"][0].endswith("ListResponse")

    create_payload = _sample_scim_user("scim-user@example.com")
    created = client.post("/api/v1/scim/v2/Users", headers=scim_headers, json=create_payload)
    assert created.status_code == 201
    created_body = created.json()
    assert created_body["schemas"][0].endswith(":User")
    assert created_body["id"]
    assert created_body["userName"] == "scim-user@example.com"
    assert created_body["active"] is True
    user_id = created_body["id"]

    created_again = client.post("/api/v1/scim/v2/Users", headers=scim_headers, json=create_payload)
    assert created_again.status_code == 200
    assert created_again.json()["id"] == user_id

    fetched = client.get(f"/api/v1/scim/v2/Users/{user_id}", headers=scim_headers)
    assert fetched.status_code == 200
    assert fetched.json()["userName"] == "scim-user@example.com"

    filtered = client.get('/api/v1/scim/v2/Users?filter=userName%20eq%20"scim-user@example.com"', headers=scim_headers)
    assert filtered.status_code == 200
    assert filtered.json()["totalResults"] == 1

    updated = client.put(
        f"/api/v1/scim/v2/Users/{user_id}",
        headers=scim_headers,
        json={
            "userName": "scim-user@example.com",
            "name": {"givenName": "Alex", "familyName": "Rivers"},
            "active": True,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["name"]["formatted"] == "Alex Rivers"

    patched = client.patch(
        f"/api/v1/scim/v2/Users/{user_id}",
        headers=scim_headers,
        json={
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [{"op": "replace", "path": "active", "value": False}],
        },
    )
    assert patched.status_code == 200
    assert patched.json()["active"] is False

    offboarding_calls: list[dict] = []

    def _fake_run_offboarding(self, org_id, deactivated_user_id, successor_id, executed_by):
        offboarding_calls.append(
            {
                "org_id": str(org_id),
                "deactivated_user_id": str(deactivated_user_id),
                "successor_id": str(successor_id),
                "executed_by": str(executed_by),
            }
        )
        return None

    monkeypatch.setattr(OffboardingService, "run_offboarding", _fake_run_offboarding)
    deleted = client.delete(f"/api/v1/scim/v2/Users/{user_id}", headers=scim_headers)
    assert deleted.status_code == 204

    user_row = db_session.get(User, UUID(user_id))
    assert user_row is not None
    assert user_row.is_active is False
    assert user_row.status == "inactive"
    assert len(offboarding_calls) == 1

    provisioned_audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == UUID(org["organization_id"]),
            AuditLog.action == "user.provisioned_via_scim",
        )
    ).scalar_one_or_none()
    assert provisioned_audit is not None
    deprovisioned_audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == UUID(org["organization_id"]),
            AuditLog.action == "user.deprovisioned_via_scim",
        )
    ).scalar_one_or_none()
    assert deprovisioned_audit is not None


def test_scim_auth_enforcement_and_org_isolation(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="scim-a")
    org_b = bootstrap_org_user(client, email_prefix="scim-b")
    _enable_scim_feature(db_session, org_a["organization_id"])
    _enable_scim_feature(db_session, org_b["organization_id"])

    token_a = _create_scim_token(client, org_a["org_headers"], "A token")
    token_b = _create_scim_token(client, org_b["org_headers"], "B token")
    headers_a = _scim_headers(token_a["raw_token"])
    headers_b = _scim_headers(token_b["raw_token"])

    create_a = client.post("/api/v1/scim/v2/Users", headers=headers_a, json=_sample_scim_user("a-only@example.com"))
    assert create_a.status_code == 201
    user_id_a = create_a.json()["id"]

    list_a = client.get("/api/v1/scim/v2/Users", headers=headers_a)
    list_b = client.get("/api/v1/scim/v2/Users", headers=headers_b)
    assert list_a.status_code == 200
    assert list_b.status_code == 200
    assert any(item["userName"] == "a-only@example.com" for item in list_a.json()["Resources"])
    assert all(item["id"] != user_id_a for item in list_b.json()["Resources"])

    invalid = client.get("/api/v1/scim/v2/Users", headers=_scim_headers("invalid-token"))
    assert invalid.status_code == 401

    jwt_token = org_a["access_token"]
    jwt_attempt = client.get("/api/v1/scim/v2/Users", headers={"Authorization": f"Bearer {jwt_token}"})
    assert jwt_attempt.status_code == 401

    expired_payload = _create_scim_token(
        client,
        org_a["org_headers"],
        "Expired token",
        expires_at=(datetime.now(UTC) - timedelta(days=1)).isoformat(),
    )
    expired_attempt = client.get("/api/v1/scim/v2/Users", headers=_scim_headers(expired_payload["raw_token"]))
    assert expired_attempt.status_code == 401

    audit_scim_tokens = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == UUID(org_a["organization_id"]),
            AuditLog.action == "scim_token.created",
        )
    ).scalars().all()
    assert len(audit_scim_tokens) >= 1


def test_scim_deprovision_does_not_disable_shared_user_in_other_org(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="scim-shared-a")
    org_b = bootstrap_org_user(client, email_prefix="scim-shared-b")
    _enable_scim_feature(db_session, org_a["organization_id"])
    _enable_scim_feature(db_session, org_b["organization_id"])

    headers_a = _scim_headers(_create_scim_token(client, org_a["org_headers"], "A token")["raw_token"])
    headers_b = _scim_headers(_create_scim_token(client, org_b["org_headers"], "B token")["raw_token"])
    payload = _sample_scim_user("shared-scim@example.com")

    created_a = client.post("/api/v1/scim/v2/Users", headers=headers_a, json=payload)
    assert created_a.status_code == 201
    user_id = created_a.json()["id"]
    created_b = client.post("/api/v1/scim/v2/Users", headers=headers_b, json=payload)
    assert created_b.status_code == 201
    assert created_b.json()["id"] == user_id

    deleted_a = client.delete(f"/api/v1/scim/v2/Users/{user_id}", headers=headers_a)
    assert deleted_a.status_code == 204

    user_row = db_session.get(User, UUID(user_id))
    assert user_row is not None
    assert user_row.is_active is True
    assert user_row.status == "active"
    membership_a = db_session.execute(
        select(Membership).where(
            Membership.organization_id == UUID(org_a["organization_id"]),
            Membership.user_id == UUID(user_id),
        )
    ).scalar_one()
    membership_b = db_session.execute(
        select(Membership).where(
            Membership.organization_id == UUID(org_b["organization_id"]),
            Membership.user_id == UUID(user_id),
        )
    ).scalar_one()
    assert membership_a.status == "inactive"
    assert membership_b.status == "active"

    fetched_b = client.get(f"/api/v1/scim/v2/Users/{user_id}", headers=headers_b)
    assert fetched_b.status_code == 200
    assert fetched_b.json()["active"] is True
