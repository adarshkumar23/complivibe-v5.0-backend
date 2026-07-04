from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.core.config import get_settings
from app.models.membership import Membership
from app.models.org_email_config import OrgEmailConfig
from app.models.role import Role
from app.models.user import User
from app.core.security import get_password_hash
from tests.helpers.auth_org import bootstrap_org_user, login_user

ADMIN_EMAIL_CONFIG_BASE = "/api/v1/admin/email-config"


@pytest.fixture(autouse=True)
def _fernet_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FERNET_SECRET_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _create_readonly_user(db_session, org_id: str, email: str) -> User:
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

    role = db_session.query(Role).filter(Role.organization_id == uuid.UUID(org_id), Role.name == "readonly").one()
    db_session.add(
        Membership(
            organization_id=uuid.UUID(org_id),
            user_id=user.id,
            role_id=role.id,
            status="active",
            invited_by=user.id,
        )
    )
    db_session.commit()
    return user


def test_admin_email_config_status_defaults_to_unconfigured(client):
    org = bootstrap_org_user(client, email_prefix="admin-email-status")

    status_resp = client.get(ADMIN_EMAIL_CONFIG_BASE, headers=org["org_headers"])
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["config_configured"] is False
    assert body["is_active"] is False
    assert body["id"] is None


def test_admin_email_config_upsert_encrypts_credentials_and_updates_status(client, db_session):
    org = bootstrap_org_user(client, email_prefix="admin-email-upsert")

    create_resp = client.post(
        ADMIN_EMAIL_CONFIG_BASE,
        headers=org["org_headers"],
        json={
            "aws_access_key_id": "AKIA_TEST",
            "aws_secret_access_key": "secret-value",
            "region": "us-east-1",
            "from_address": "alerts@example.com",
            "is_active": True,
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    body = create_resp.json()
    assert body["config_configured"] is True
    assert body["is_active"] is True
    assert body["provider"] == "ses"

    row = db_session.execute(
        select(OrgEmailConfig).where(OrgEmailConfig.organization_id == uuid.UUID(org["organization_id"]))
    ).scalar_one()
    # Credentials must never be stored in plaintext.
    assert "secret-value" not in row.config_json
    assert "AKIA_TEST" not in row.config_json

    from app.privacy.services.email_config_service import EmailConfigService

    decrypted = EmailConfigService.decrypt_config(row.config_json)
    assert decrypted["aws_access_key_id"] == "AKIA_TEST"
    assert decrypted["from_address"] == "alerts@example.com"

    status_resp = client.get(ADMIN_EMAIL_CONFIG_BASE, headers=org["org_headers"])
    assert status_resp.status_code == 200
    assert status_resp.json()["config_configured"] is True

    # Upsert again with a new region should update the same row, not create a second one.
    update_resp = client.post(
        ADMIN_EMAIL_CONFIG_BASE,
        headers=org["org_headers"],
        json={
            "aws_access_key_id": "AKIA_TEST",
            "aws_secret_access_key": "secret-value-2",
            "region": "eu-west-1",
            "from_address": "alerts@example.com",
            "is_active": True,
        },
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["id"] == body["id"]

    count = db_session.execute(
        select(OrgEmailConfig).where(OrgEmailConfig.organization_id == uuid.UUID(org["organization_id"]))
    ).scalars().all()
    assert len(count) == 1


def test_admin_email_config_test_send_and_non_admin_forbidden(client, db_session):
    org = bootstrap_org_user(client, email_prefix="admin-email-test")

    client.post(
        ADMIN_EMAIL_CONFIG_BASE,
        headers=org["org_headers"],
        json={
            "aws_access_key_id": "AKIA_TEST",
            "aws_secret_access_key": "secret-value",
            "region": "us-east-1",
            "from_address": "alerts@example.com",
            "is_active": True,
        },
    )

    with patch(
        "app.compliance.services.email_delivery_service.SESEmailDeliveryService.send",
        return_value=True,
    ):
        test_resp = client.post(
            f"{ADMIN_EMAIL_CONFIG_BASE}/test",
            headers=org["org_headers"],
            json={},
        )
    assert test_resp.status_code == 200, test_resp.text
    assert test_resp.json()["success"] is True

    readonly_user = _create_readonly_user(db_session, org["organization_id"], "readonly-admin-email@example.com")
    token = login_user(client, readonly_user.email)
    ro_headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["organization_id"]}

    denied = client.post(
        ADMIN_EMAIL_CONFIG_BASE,
        headers=ro_headers,
        json={
            "aws_access_key_id": "AKIA_TEST",
            "aws_secret_access_key": "secret-value",
            "region": "us-east-1",
            "from_address": "alerts@example.com",
        },
    )
    assert denied.status_code == 403

    denied_get = client.get(ADMIN_EMAIL_CONFIG_BASE, headers=ro_headers)
    assert denied_get.status_code == 403
