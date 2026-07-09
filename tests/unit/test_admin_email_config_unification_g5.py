from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.core.config import get_settings
from app.models.org_email_config import OrgEmailConfig
from app.platform.services.ses_service import SESService
from tests.helpers.auth_org import bootstrap_org_user


@pytest.fixture(autouse=True)
def _ses_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AWS_SES_ACCESS_KEY_ID", "platform_key")
    monkeypatch.setenv("AWS_SES_SECRET_ACCESS_KEY", "platform_secret")
    monkeypatch.setenv("AWS_SES_REGION", "ap-south-1")
    monkeypatch.setenv("AWS_SES_FROM_EMAIL", "platform@example.com")
    monkeypatch.setenv("AWS_SES_FROM_NAME", "CompliVibe")
    monkeypatch.setenv("FERNET_SECRET_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@patch("app.platform.services.ses_service.boto3.client")
def test_admin_email_config_upsert_is_honored_by_the_real_send_path(mock_boto_client, client, db_session):
    """Regression test for the two-unsynced-email-configs bug.

    Before the fix, POST /api/v1/admin/email-config wrote only to the legacy
    `config_json` blob and never flipped `use_platform_ses` to False, so
    `SESService._resolve_client` (the real send path used everywhere email
    actually goes out) silently kept using the platform's default sender no
    matter what an org admin configured through this endpoint.
    """
    mock_boto_client.return_value = MagicMock()

    org = bootstrap_org_user(client, email_prefix="admincfg")

    resp = client.post(
        "/api/v1/admin/email-config",
        headers=org["org_headers"],
        json={
            "aws_access_key_id": "org_admin_key",
            "aws_secret_access_key": "org_admin_secret",
            "region": "eu-west-1",
            "from_address": "org-admin-sender@example.com",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["config_configured"] is True

    cfg = db_session.execute(
        select(OrgEmailConfig).where(OrgEmailConfig.organization_id == uuid.UUID(org["organization_id"]))
    ).scalar_one()

    # The canonical columns the real send path reads must now be populated.
    assert cfg.use_platform_ses is False
    assert cfg.aws_access_key_id_enc is not None
    assert cfg.aws_secret_key_enc is not None
    assert cfg.aws_region == "eu-west-1"
    assert cfg.from_email == "org-admin-sender@example.com"

    ses = SESService()
    assert ses.decrypt_credential(cfg.aws_access_key_id_enc) == "org_admin_key"
    assert ses.decrypt_credential(cfg.aws_secret_key_enc) == "org_admin_secret"

    # The real resolver must select the org's custom sender/credentials, not
    # the platform default, given only the config set via the admin endpoint.
    client_used, from_email, from_name, reply_to = ses._resolve_client(
        org_id=uuid.UUID(org["organization_id"]),
        db=db_session,
    )
    assert from_email == "org-admin-sender@example.com"
