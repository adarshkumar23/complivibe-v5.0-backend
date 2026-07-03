from __future__ import annotations

from uuid import UUID
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import _configure_sentry, _scrub_sensitive_data
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user


def _promote_superuser(db_session, user_id: str) -> None:
    user = db_session.get(User, UUID(user_id))
    assert user is not None
    user.is_superuser = True
    db_session.flush()


def test_sentry_setting_defaults_exist():
    settings = get_settings()
    assert settings.SENTRY_DSN == ""
    assert settings.SENTRY_ENVIRONMENT == "production"
    assert settings.SENTRY_TRACES_SAMPLE_RATE == 0.1


def test_sentry_not_initialized_when_dsn_empty(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "")
    get_settings.cache_clear()

    with patch("app.main.sentry_sdk.init") as sentry_init:
        _configure_sentry()
        sentry_init.assert_not_called()


def test_scrub_sensitive_data_redacts_expected_fields():
    event = {
        "request": {
            "headers": {
                "authorization": "Bearer abc",
                "x-complivibe-key": "sensitive",
                "email": "user@example.com",
            },
            "data": {
                "password": "secret-password",
                "token": "jwt-token",
                "api_key": "k",
                "org_name": "Acme",
            },
        },
        "extra": {
            "secret": "keep-out",
            "aws_secret_access_key": "aws-secret",
            "nested": {"hashed_password": "h", "email": "a@b.com"},
        },
    }

    scrubbed = _scrub_sensitive_data(event)
    assert scrubbed["request"]["data"]["password"] == "[REDACTED]"
    assert scrubbed["request"]["data"]["token"] == "[REDACTED]"
    assert scrubbed["request"]["data"]["api_key"] == "[REDACTED]"
    assert scrubbed["request"]["headers"]["authorization"] == "[REDACTED]"
    assert scrubbed["extra"]["secret"] == "[REDACTED]"
    assert scrubbed["extra"]["aws_secret_access_key"] == "[REDACTED]"
    assert scrubbed["extra"]["nested"]["hashed_password"] == "[REDACTED]"

    assert scrubbed["request"]["headers"]["email"] == "user@example.com"
    assert scrubbed["request"]["data"]["org_name"] == "Acme"
    assert scrubbed["extra"]["nested"]["email"] == "a@b.com"


def test_admin_sentry_test_endpoint_permissions_and_behavior(client, db_session):
    regular = bootstrap_org_user(client, email_prefix="sentry-regular")
    forbidden = client.get("/api/v1/admin/sentry-test", headers=regular["headers"])
    assert forbidden.status_code == 403

    elevated = bootstrap_org_user(client, email_prefix="sentry-super")
    _promote_superuser(db_session, elevated["user_id"])

    with TestClient(client.app, raise_server_exceptions=False) as no_raise_client:
        response = no_raise_client.get("/api/v1/admin/sentry-test", headers=elevated["headers"])
    assert response.status_code == 500
