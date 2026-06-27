import base64
import hashlib
import json
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.membership import Membership
from app.models.org_email_config import OrgEmailConfig
from app.models.role import Role
from app.models.user import User
from app.services.audit_service import AuditService


class EmailConfigService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _fernet() -> Fernet:
        settings = get_settings()
        key_value = getattr(settings, "EMAIL_CONFIG_ENCRYPTION_KEY", None) or settings.SECRET_KEY
        digest = hashlib.sha256(key_value.encode("utf-8")).digest()
        return Fernet(base64.urlsafe_b64encode(digest))

    @classmethod
    def encrypt_config(cls, config: dict) -> str:
        payload = json.dumps(config, sort_keys=True)
        return cls._fernet().encrypt(payload.encode("utf-8")).decode("utf-8")

    @classmethod
    def decrypt_config(cls, config_json: str) -> dict:
        raw = cls._fernet().decrypt(config_json.encode("utf-8")).decode("utf-8")
        return json.loads(raw)

    def _require_admin_membership(self, membership: Membership) -> None:
        role = self.db.get(Role, membership.role_id)
        if role is None or role.name not in {"owner", "admin"}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Org admin role required")

    def get_config(self, org_id: uuid.UUID) -> OrgEmailConfig | None:
        return self.db.execute(select(OrgEmailConfig).where(OrgEmailConfig.organization_id == org_id)).scalar_one_or_none()

    def get_active_config(self, org_id: uuid.UUID) -> OrgEmailConfig | None:
        return self.db.execute(
            select(OrgEmailConfig).where(
                OrgEmailConfig.organization_id == org_id,
                OrgEmailConfig.is_active.is_(True),
            )
        ).scalar_one_or_none()

    def upsert_config(self, org_id: uuid.UUID, data, created_by: uuid.UUID, membership: Membership) -> OrgEmailConfig:
        self._require_admin_membership(membership)

        payload = data.model_dump()
        encrypted = self.encrypt_config(
            {
                "aws_access_key_id": payload["aws_access_key_id"],
                "aws_secret_access_key": payload["aws_secret_access_key"],
                "region": payload["region"],
                "from_address": str(payload["from_address"]),
            }
        )

        now = self.utcnow()
        row = self.get_config(org_id)
        action = "org_email_config.created"
        if row is None:
            row = OrgEmailConfig(
                organization_id=org_id,
                provider="ses",
                config_json=encrypted,
                is_active=bool(payload.get("is_active", True)),
                test_sent_at=None,
                created_by=created_by,
                created_at=now,
                updated_at=now,
            )
            self.db.add(row)
        else:
            row.provider = "ses"
            row.config_json = encrypted
            row.is_active = bool(payload.get("is_active", row.is_active))
            row.updated_at = now
            action = "org_email_config.updated"

        self.db.flush()
        AuditService(self.db).write_audit_log(
            action=action,
            entity_type="org_email_config",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={"provider": row.provider, "is_active": row.is_active},
            metadata_json={"source": "api"},
        )
        return row

    def send_test_email(
        self,
        org_id: uuid.UUID,
        membership: Membership,
        actor_user_id: uuid.UUID,
        to_address: str | None = None,
    ) -> tuple[bool, str]:
        self._require_admin_membership(membership)

        row = self.get_active_config(org_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active email config found")

        config = self.decrypt_config(row.config_json)
        destination = to_address
        if not destination:
            owner_user = self.db.execute(
                select(User)
                .join(Membership, Membership.user_id == User.id)
                .join(Role, Role.id == Membership.role_id)
                .where(
                    Membership.organization_id == org_id,
                    Membership.status == "active",
                    Role.name == "owner",
                    User.is_active.is_(True),
                    User.status == "active",
                    User.email.is_not(None),
                )
                .order_by(Membership.created_at.asc())
            ).scalars().first()
            if owner_user is None:
                owner_user = self.db.get(User, actor_user_id)
            if owner_user is None or not owner_user.email:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No destination email available")
            destination = owner_user.email

        from app.compliance.services.email_delivery_service import SESEmailDeliveryService

        sender = SESEmailDeliveryService(
            aws_access_key_id=config["aws_access_key_id"],
            aws_secret_access_key=config["aws_secret_access_key"],
            region=config["region"],
            from_address=config["from_address"],
        )
        ok = sender.send(
            to=destination,
            subject="CompliVibe SES configuration test",
            html_body="<p>This is a CompliVibe SES configuration test email.</p>",
            text_body="This is a CompliVibe SES configuration test email.",
        )
        if not ok:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="SES test email failed")

        row.test_sent_at = self.utcnow()
        row.updated_at = row.test_sent_at
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="org_email_config.test_sent",
            entity_type="org_email_config",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={"test_sent_at": row.test_sent_at.isoformat(), "sent_to": destination},
            metadata_json={"source": "api"},
        )
        return True, destination
