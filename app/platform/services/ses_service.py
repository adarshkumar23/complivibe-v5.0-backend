from __future__ import annotations

import base64
import hashlib
import uuid
from typing import Any

import boto3
from botocore.exceptions import ClientError
from cryptography.fernet import Fernet
try:
    import sentry_sdk
except Exception:  # pragma: no cover - optional in local test environments
    sentry_sdk = None  # type: ignore[assignment]
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.org_email_config import OrgEmailConfig


class SESService:
    def __init__(self) -> None:
        settings = get_settings()
        self.platform_client = boto3.client(
            "ses",
            region_name=settings.AWS_SES_REGION,
            aws_access_key_id=settings.AWS_SES_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SES_SECRET_ACCESS_KEY,
        )
        self.platform_from_email = settings.AWS_SES_FROM_EMAIL
        self.platform_from_name = settings.AWS_SES_FROM_NAME
        self.fernet = Fernet(self._resolve_fernet_key())

    @staticmethod
    def _resolve_fernet_key() -> bytes:
        settings = get_settings()
        raw = (settings.FERNET_SECRET_KEY or "").strip()
        if raw:
            return raw.encode("utf-8")

        # Backward-compatible fallback to a deterministic Fernet key from SECRET_KEY.
        digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)

    def encrypt_credential(self, value: str) -> str:
        return self.fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt_credential(self, value: str) -> str:
        return self.fernet.decrypt(value.encode("utf-8")).decode("utf-8")

    def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str | None = None,
        org_id: uuid.UUID | None = None,
        reply_to: str | None = None,
        db: Session | None = None,
    ) -> dict[str, Any]:
        client, from_addr, from_name, resolved_reply_to = self._resolve_client(org_id=org_id, db=db)

        source = f"{from_name} <{from_addr}>" if from_name else from_addr
        body: dict[str, dict[str, str]] = {}
        if html_body:
            body["Html"] = {"Data": html_body, "Charset": "UTF-8"}
        if text_body:
            body["Text"] = {"Data": text_body, "Charset": "UTF-8"}
        if not body:
            body["Text"] = {"Data": "", "Charset": "UTF-8"}

        reply_to_addresses: list[str] = []
        if reply_to:
            reply_to_addresses = [reply_to]
        elif resolved_reply_to:
            reply_to_addresses = [resolved_reply_to]

        try:
            response = client.send_email(
                Source=source,
                Destination={"ToAddresses": [to_email]},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": body,
                },
                ReplyToAddresses=reply_to_addresses,
            )
            return {
                "success": True,
                "message_id": response.get("MessageId"),
                "error": None,
            }
        except ClientError as exc:
            settings = get_settings()
            if settings.SENTRY_DSN and sentry_sdk is not None:
                sentry_sdk.capture_exception(exc)
            err = exc.response.get("Error", {})
            code = err.get("Code", "Unknown")
            msg = err.get("Message", str(exc))
            return {
                "success": False,
                "message_id": None,
                "error": f"{code}: {msg}",
            }

    def send_bulk(self, emails: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for email in emails:
            result = self.send_email(
                to_email=email["to"],
                subject=email["subject"],
                html_body=email.get("html", ""),
                text_body=email.get("text"),
                org_id=email.get("org_id"),
                reply_to=email.get("reply_to"),
                db=email.get("db"),
            )
            result["to"] = email["to"]
            results.append(result)
        return results

    def verify_credentials(
        self,
        *,
        access_key_id: str,
        secret_access_key: str,
        region: str,
        from_email: str,
    ) -> dict[str, Any]:
        try:
            test_client = boto3.client(
                "ses",
                region_name=region,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
            )
            verification = test_client.get_identity_verification_attributes(Identities=[from_email])
            attrs = verification.get("VerificationAttributes", {})
            status = attrs.get(from_email, {}).get("VerificationStatus", "NotFound")
            quota = test_client.get_send_quota()
            return {
                "valid": True,
                "sender_verified": status == "Success",
                "email_verification_status": status,
                "max_24h_send": quota.get("Max24HourSend", 0),
                "sent_last_24h": quota.get("SentLast24Hours", 0),
            }
        except ClientError as exc:
            msg = exc.response.get("Error", {}).get("Message", str(exc))
            return {
                "valid": False,
                "error": msg,
            }

    def _resolve_client(
        self,
        *,
        org_id: uuid.UUID | None,
        db: Session | None,
    ) -> tuple[Any, str, str | None, str | None]:
        if org_id is not None and db is not None:
            config = db.execute(
                select(OrgEmailConfig).where(
                    OrgEmailConfig.organization_id == org_id,
                    OrgEmailConfig.is_active.is_(True),
                )
            ).scalar_one_or_none()

            if config is not None and not bool(getattr(config, "use_platform_ses", True)):
                # New-format encrypted credentials take precedence.
                if config.aws_access_key_id_enc and config.aws_secret_key_enc:
                    try:
                        access_key = self.decrypt_credential(config.aws_access_key_id_enc)
                        secret_key = self.decrypt_credential(config.aws_secret_key_enc)
                        org_client = boto3.client(
                            "ses",
                            region_name=config.aws_region or "ap-south-1",
                            aws_access_key_id=access_key,
                            aws_secret_access_key=secret_key,
                        )
                        return (
                            org_client,
                            config.from_email or self.platform_from_email,
                            config.from_name,
                            config.reply_to_email,
                        )
                    except Exception:
                        pass

                # Backward-compatible fallback for legacy encrypted JSON config.
                if config.config_json:
                    try:
                        from app.privacy.services.email_config_service import EmailConfigService

                        creds = EmailConfigService.decrypt_config(config.config_json)
                        org_client = boto3.client(
                            "ses",
                            region_name=creds.get("region") or "ap-south-1",
                            aws_access_key_id=creds["aws_access_key_id"],
                            aws_secret_access_key=creds["aws_secret_access_key"],
                        )
                        return (
                            org_client,
                            creds.get("from_address") or self.platform_from_email,
                            config.from_name,
                            config.reply_to_email,
                        )
                    except Exception:
                        pass

        return (self.platform_client, self.platform_from_email, self.platform_from_name, None)
