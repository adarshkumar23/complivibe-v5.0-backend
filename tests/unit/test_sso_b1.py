from __future__ import annotations

from uuid import UUID

from sqlalchemy import inspect, select

from app.auth.services.sso_service import SSOService
from app.models.audit_log import AuditLog
from app.models.membership import Membership
from app.models.sso_config import SSOConfig
from app.models.user import User
from app.models.organization import Organization
from tests.helpers.auth_org import bootstrap_org_user


def _org_slug(client, headers: dict[str, str]) -> str:
    response = client.get("/api/v1/organizations/me", headers=headers)
    assert response.status_code == 200
    return response.json()[0]["slug"]


def _sample_config_payload() -> dict:
    return {
        "provider": "okta",
        "entity_id": "https://example.okta.com/app/issuer",
        "sso_url": "https://example.okta.com/app/sso/saml",
        "slo_url": "https://example.okta.com/app/slo/saml",
        "certificate": "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----",
        "attribute_mapping": {
            "email": "NameID",
            "first_name": "firstName",
            "last_name": "lastName",
            "role": "groups",
        },
        "jit_provisioning": True,
        "default_role": "member",
    }


def _enable_sso_feature(db_session, organization_id: str) -> None:
    org = db_session.get(Organization, UUID(organization_id))
    assert org is not None
    org.subscription_status = "active"
    org.subscription_plan = "growth"
    db_session.commit()


def test_sso_config_end_to_end_and_public_endpoints(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="sso-a")
    org_b = bootstrap_org_user(client, email_prefix="sso-b")
    _enable_sso_feature(db_session, org_a["organization_id"])
    _enable_sso_feature(db_session, org_b["organization_id"])
    slug_a = _org_slug(client, org_a["headers"])

    tables = set(inspect(db_session.bind).get_table_names())
    assert "sso_configs" in tables

    create_resp = client.post("/api/v1/sso-configs", headers=org_a["org_headers"], json=_sample_config_payload())
    assert create_resp.status_code == 201
    config_id = create_resp.json()["id"]

    duplicate = client.post("/api/v1/sso-configs", headers=org_a["org_headers"], json=_sample_config_payload())
    assert duplicate.status_code == 409

    metadata = client.get(f"/api/v1/auth/sso/{slug_a}/metadata")
    assert metadata.status_code == 200
    assert "xml" in metadata.headers.get("content-type", "")
    assert f"/auth/sso/{slug_a}/callback" in metadata.text

    initiate = client.post(f"/api/v1/auth/sso/{slug_a}/initiate")
    assert initiate.status_code == 400

    activate = client.post(f"/api/v1/sso-configs/{config_id}/activate", headers=org_a["org_headers"])
    assert activate.status_code == 200
    assert activate.json()["is_active"] is True

    initiate = client.post(f"/api/v1/auth/sso/{slug_a}/initiate")
    assert initiate.status_code == 200
    assert "redirect_url" in initiate.json()
    assert _sample_config_payload()["sso_url"] in initiate.json()["redirect_url"]

    get_cfg = client.get("/api/v1/sso-configs", headers=org_a["org_headers"])
    assert get_cfg.status_code == 200
    assert "certificate" not in get_cfg.json()

    other_org_get = client.get("/api/v1/sso-configs", headers=org_b["org_headers"])
    assert other_org_get.status_code == 404

    tested = client.post(f"/api/v1/sso-configs/{config_id}/test", headers=org_a["org_headers"])
    assert tested.status_code == 200
    assert set(tested.json().keys()) == {"valid", "errors"}

    deactivated = client.post(f"/api/v1/sso-configs/{config_id}/deactivate", headers=org_a["org_headers"])
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    deleted = client.delete(f"/api/v1/sso-configs/{config_id}", headers=org_a["org_headers"])
    assert deleted.status_code == 204

    row = db_session.get(SSOConfig, UUID(config_id))
    assert row is not None
    assert row.deleted_at is not None


def test_sso_callback_jit_and_existing_user_and_audit_log(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="sso-callback")
    _enable_sso_feature(db_session, org["organization_id"])
    slug = _org_slug(client, org["headers"])

    create_resp = client.post("/api/v1/sso-configs", headers=org["org_headers"], json=_sample_config_payload())
    assert create_resp.status_code == 201
    config_id = create_resp.json()["id"]
    activate = client.post(f"/api/v1/sso-configs/{config_id}/activate", headers=org["org_headers"])
    assert activate.status_code == 200

    monkeypatch.setattr(SSOService, "_extract_email", lambda self, saml_response, config: "jit-user@example.com")
    callback = client.post(f"/api/v1/auth/sso/{slug}/callback", data={"SAMLResponse": "mock-response"})
    assert callback.status_code == 200
    payload = callback.json()
    assert payload["auth_method"] == "sso"
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]

    user = db_session.execute(select(User).where(User.email == "jit-user@example.com")).scalar_one_or_none()
    assert user is not None
    membership = db_session.execute(
        select(Membership).where(
            Membership.organization_id == UUID(org["organization_id"]),
            Membership.user_id == user.id,
        )
    ).scalar_one_or_none()
    assert membership is not None

    before_count = db_session.execute(select(User)).scalars().all()
    monkeypatch.setattr(SSOService, "_extract_email", lambda self, saml_response, config: "jit-user@example.com")
    callback_existing = client.post(f"/api/v1/auth/sso/{slug}/callback", data={"SAMLResponse": "mock-response"})
    assert callback_existing.status_code == 200
    after_count = db_session.execute(select(User)).scalars().all()
    assert len(after_count) == len(before_count)

    audit_row = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == UUID(org["organization_id"]),
            AuditLog.action == "sso.login",
        )
    ).scalars().first()
    assert audit_row is not None


def test_sso_callback_rejects_unsigned_forged_assertion(client, db_session):
    org = bootstrap_org_user(client, email_prefix="sso-forged")
    _enable_sso_feature(db_session, org["organization_id"])
    slug = _org_slug(client, org["headers"])

    create_resp = client.post("/api/v1/sso-configs", headers=org["org_headers"], json=_sample_config_payload())
    assert create_resp.status_code == 201
    config_id = create_resp.json()["id"]
    activate = client.post(f"/api/v1/sso-configs/{config_id}/activate", headers=org["org_headers"])
    assert activate.status_code == 200

    forged = "<saml:NameID>attacker@example.com</saml:NameID>"
    callback = client.post(f"/api/v1/auth/sso/{slug}/callback", data={"SAMLResponse": forged})
    assert callback.status_code == 400


def test_sso_callback_jit_disabled_unknown_user_returns_401(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="sso-disabled")
    _enable_sso_feature(db_session, org["organization_id"])
    slug = _org_slug(client, org["headers"])

    payload = _sample_config_payload()
    payload["jit_provisioning"] = False
    create_resp = client.post("/api/v1/sso-configs", headers=org["org_headers"], json=payload)
    assert create_resp.status_code == 201
    config_id = create_resp.json()["id"]

    activate = client.post(f"/api/v1/sso-configs/{config_id}/activate", headers=org["org_headers"])
    assert activate.status_code == 200

    monkeypatch.setattr(SSOService, "_extract_email", lambda self, saml_response, config: "unknown-user@example.com")
    callback = client.post(f"/api/v1/auth/sso/{slug}/callback", data={"SAMLResponse": "mock-response"})
    assert callback.status_code == 401
