from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import inspect, select

from app.core.config import Settings, get_settings
from app.models.email_outbox import EmailOutbox
from app.models.membership import Membership
from app.models.org_email_config import OrgEmailConfig
from app.models.role import Role
from app.models.user import User
from app.platform.services.email_outbox_flush_service import EmailOutboxFlushService
from app.platform.services.ses_service import SESService
from app.core.security import get_password_hash
from tests.helpers.auth_org import bootstrap_org_user, login_user


@pytest.fixture(autouse=True)
def _ses_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AWS_SES_ACCESS_KEY_ID", "ses_key")
    monkeypatch.setenv("AWS_SES_SECRET_ACCESS_KEY", "ses_secret")
    monkeypatch.setenv("AWS_SES_REGION", "ap-south-1")
    monkeypatch.setenv("AWS_SES_FROM_EMAIL", "noreply@example.com")
    monkeypatch.setenv("AWS_SES_FROM_NAME", "CompliVibe")
    monkeypatch.setenv("FERNET_SECRET_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _create_outbox(db_session, org_id: uuid.UUID, recipient: str, status: str = "pending") -> EmailOutbox:
    row = EmailOutbox(
        organization_id=org_id,
        template_id=None,
        event_type="test.email",
        template_name=None,
        template_context=None,
        recipient_email=recipient,
        recipient_user_id=None,
        subject="Subject",
        body_text="Body",
        body_html="<p>Body</p>",
        status=status,
        priority="normal",
        scheduled_at=None,
        queued_at=datetime.now(UTC),
        sent_at=None,
        failed_at=None,
        cancelled_at=None,
        locked_at=None,
        locked_by=None,
        lock_expires_at=None,
        last_attempt_at=None,
        next_attempt_at=None,
        dead_lettered_at=None,
        attempt_count=0,
        max_attempts=3,
        retry_count=0,
        last_error=None,
        provider=None,
        provider_message_id=None,
        ses_message_id=None,
        metadata_json=None,
        worker_metadata_json=None,
        created_by_user_id=None,
    )
    db_session.add(row)
    db_session.flush()
    return row


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


def test_schema_columns_exist_for_org_email_configs_and_outbox(db_session):
    tables = set(inspect(db_session.bind).get_table_names())
    assert "org_email_configs" in tables

    cols = {c["name"] for c in inspect(db_session.bind).get_columns("org_email_configs")}
    assert "use_platform_ses" in cols
    assert "aws_access_key_id_enc" in cols

    outbox_cols = {c["name"] for c in inspect(db_session.bind).get_columns("email_outbox")}
    assert "ses_message_id" in outbox_cols
    assert "retry_count" in outbox_cols


def test_encrypt_decrypt_and_wrong_key_fails(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ses-crypto")
    org_id = uuid.UUID(org["organization_id"])

    svc = SESService()
    value = "secret-value"
    enc = svc.encrypt_credential(value, db=db_session, organization_id=org_id)
    assert enc != value
    assert enc.startswith("vault:")
    assert svc.decrypt_credential(enc, db=db_session, organization_id=org_id) == value

    # A legacy Fernet token encrypted under a different key must not decrypt.
    other = Fernet(Fernet.generate_key())
    legacy_token = other.encrypt(value.encode("utf-8")).decode("utf-8")
    with pytest.raises(Exception):
        svc.decrypt_credential(legacy_token, db=db_session, organization_id=org_id)


@patch("app.platform.services.ses_service.boto3.client")
def test_send_email_success_and_failure(mock_boto_client):
    platform_client = MagicMock()
    platform_client.send_email.return_value = {"MessageId": "mid_1"}
    mock_boto_client.return_value = platform_client

    svc = SESService()
    ok = svc.send_email(
        to_email="to@example.com",
        subject="Hello",
        html_body="<p>Hi</p>",
        text_body="Hi",
    )
    assert ok["success"] is True
    assert ok["message_id"] == "mid_1"

    from botocore.exceptions import ClientError

    platform_client.send_email.side_effect = ClientError(
        error_response={"Error": {"Code": "MessageRejected", "Message": "Rejected"}},
        operation_name="SendEmail",
    )
    bad = svc.send_email(
        to_email="to@example.com",
        subject="Hello",
        html_body="<p>Hi</p>",
        text_body="Hi",
    )
    assert bad["success"] is False
    assert "MessageRejected" in bad["error"]


@patch("app.platform.services.ses_service.boto3.client")
def test_send_bulk_and_verify_credentials_and_org_custom_client(mock_boto_client, db_session):
    platform_client = MagicMock()
    platform_client.send_email.return_value = {"MessageId": "platform_mid"}

    org_client = MagicMock()
    org_client.send_email.return_value = {"MessageId": "org_mid"}

    verify_client = MagicMock()
    verify_client.get_identity_verification_attributes.return_value = {
        "VerificationAttributes": {"sender@example.com": {"VerificationStatus": "Success"}}
    }
    verify_client.get_send_quota.return_value = {"Max24HourSend": 1000, "SentLast24Hours": 10}

    # SESService init -> platform client; org resolution -> org client; verify_credentials -> verify client
    mock_boto_client.side_effect = [platform_client, org_client, verify_client]

    svc = SESService()

    org_id = uuid.uuid4()
    creator = User(
        email="creator@example.com",
        full_name="creator",
        hashed_password=get_password_hash("Pass1234!@"),
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(creator)
    db_session.flush()

    cfg = OrgEmailConfig(
        organization_id=org_id,
        provider="ses",
        config_json="{}",
        is_active=True,
        test_sent_at=None,
        created_by=creator.id,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        use_platform_ses=False,
        aws_access_key_id_enc=svc.encrypt_credential("org_key", db=db_session, organization_id=org_id),
        aws_secret_key_enc=svc.encrypt_credential("org_secret", db=db_session, organization_id=org_id),
        aws_region="ap-south-1",
        from_email="sender@example.com",
        from_name="Org Sender",
        reply_to_email="reply@example.com",
        daily_send_limit=1000,
        sent_today=0,
    )
    db_session.add(cfg)
    db_session.flush()

    sent = svc.send_email(
        to_email="to@example.com",
        subject="Org",
        html_body="<p>Org</p>",
        org_id=org_id,
        db=db_session,
    )
    assert sent["success"] is True
    assert sent["message_id"] == "org_mid"

    bulk = svc.send_bulk(
        [
            {"to": "a@example.com", "subject": "A", "html": "<p>A</p>"},
            {"to": "b@example.com", "subject": "B", "html": "<p>B</p>"},
            {"to": "c@example.com", "subject": "C", "html": "<p>C</p>"},
        ]
    )
    assert len(bulk) == 3

    verified = svc.verify_credentials(
        access_key_id="k",
        secret_access_key="s",
        region="ap-south-1",
        from_email="sender@example.com",
    )
    assert verified["valid"] is True
    assert verified["sender_verified"] is True


@patch("app.platform.services.email_outbox_flush_service.SESService.send_email")
@patch("app.platform.services.ses_service.boto3.client")
def test_outbox_flush_behaviors(mock_boto_client, mock_send_email, db_session, client):
    mock_boto_client.return_value = MagicMock()

    org = bootstrap_org_user(client, email_prefix="ses-flush")
    org_id = uuid.UUID(org["organization_id"])

    ok_row = _create_outbox(db_session, org_id, "ok@example.com", status="pending")
    fail_row = _create_outbox(db_session, org_id, "fail@example.com", status="pending")

    mock_send_email.side_effect = [
        {"success": True, "message_id": "m1", "error": None},
        {"success": False, "message_id": None, "error": "Rejected"},
    ]

    result = EmailOutboxFlushService(db_session).flush(batch_size=50)
    assert result["sent"] == 1
    assert result["failed"] == 1
    assert result["total_processed"] >= 2

    db_session.refresh(ok_row)
    assert ok_row.status == "sent"
    assert ok_row.sent_at is not None

    db_session.refresh(fail_row)
    assert fail_row.retry_count == 1
    assert fail_row.status == "pending"

    # Third retry fails -> terminal failed
    fail_row.retry_count = 2
    fail_row.attempt_count = 2
    fail_row.next_attempt_at = datetime.now(UTC)
    db_session.flush()
    mock_send_email.side_effect = [{"success": False, "message_id": None, "error": "Rejected"}]
    EmailOutboxFlushService(db_session).flush(batch_size=50)
    db_session.refresh(fail_row)
    assert fail_row.status == "failed"

    for i in range(60):
        _create_outbox(db_session, org_id, f"bulk{i}@example.com", status="pending")
    db_session.flush()
    mock_send_email.side_effect = [{"success": True, "message_id": f"bulk-{i}", "error": None} for i in range(100)]
    batch = EmailOutboxFlushService(db_session).flush(batch_size=50)
    assert batch["total_processed"] == 50


@patch("app.platform.services.ses_service.boto3.client")
def test_admin_email_config_endpoints_and_non_admin_forbidden(mock_boto_client, client, db_session):
    mock_client = MagicMock()
    mock_client.send_email.return_value = {"MessageId": "test_mid"}
    mock_client.get_identity_verification_attributes.return_value = {
        "VerificationAttributes": {"sender@example.com": {"VerificationStatus": "Success"}}
    }
    mock_client.get_send_quota.return_value = {"Max24HourSend": 1000, "SentLast24Hours": 10}
    mock_boto_client.return_value = mock_client

    org = bootstrap_org_user(client, email_prefix="ses-admin")

    create_platform = client.post(
        "/api/v1/email-config",
        headers=org["org_headers"],
        json={"use_platform_ses": True, "daily_send_limit": 2000},
    )
    assert create_platform.status_code == 200, create_platform.text
    assert create_platform.json()["use_platform_ses"] is True

    with patch("app.platform.services.ses_service.SESService.verify_credentials", return_value={"valid": True, "sender_verified": True}):
        create_custom = client.post(
            "/api/v1/email-config",
            headers=org["org_headers"],
            json={
                "use_platform_ses": False,
                "aws_access_key_id": "org_key",
                "aws_secret_access_key": "org_secret",
                "aws_region": "ap-south-1",
                "from_email": "sender@example.com",
                "from_name": "Org Sender",
            },
        )
    assert create_custom.status_code == 200, create_custom.text

    cfg = db_session.execute(
        select(OrgEmailConfig).where(OrgEmailConfig.organization_id == uuid.UUID(org["organization_id"]))
    ).scalar_one()
    assert cfg.aws_access_key_id_enc is not None
    assert cfg.aws_secret_key_enc is not None

    get_cfg = client.get("/api/v1/email-config", headers=org["org_headers"])
    assert get_cfg.status_code == 200
    body = get_cfg.json()
    assert "aws_access_key_id_enc" not in body
    assert "aws_secret_key_enc" not in body

    with patch(
        "app.platform.services.ses_service.SESService.send_email",
        return_value={"success": True, "message_id": "msg_1", "error": None},
    ):
        test_resp = client.post("/api/v1/email-config/test", headers=org["org_headers"])
    assert test_resp.status_code == 200
    assert test_resp.json()["success"] is True

    readonly_user = _create_readonly_user(db_session, org["organization_id"], "readonly-ses@example.com")
    token = login_user(client, readonly_user.email)
    ro_headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["organization_id"]}

    denied = client.post("/api/v1/email-config", headers=ro_headers, json={"use_platform_ses": True})
    assert denied.status_code == 403


def test_settings_include_ses_and_fernet_fields(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECRET_KEY", "test_secret_key_that_is_long_enough")
    monkeypatch.setenv("AWS_SES_ACCESS_KEY_ID", "k")
    monkeypatch.setenv("AWS_SES_REGION", "ap-south-1")
    monkeypatch.setenv("FERNET_SECRET_KEY", Fernet.generate_key().decode())

    settings = Settings()
    assert hasattr(settings, "AWS_SES_ACCESS_KEY_ID")
    assert hasattr(settings, "AWS_SES_REGION")
    assert hasattr(settings, "FERNET_SECRET_KEY")
