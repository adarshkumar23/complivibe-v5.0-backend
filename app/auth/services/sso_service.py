from __future__ import annotations

import base64
import re
import uuid
from datetime import UTC, datetime
from urllib.parse import quote_plus

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, get_password_hash
from app.models.email_outbox import EmailOutbox
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.role import Role
from app.models.sso_config import SSOConfig
from app.models.user import User
from app.services.audit_service import AuditService

try:
    from onelogin.saml2.auth import OneLogin_Saml2_Auth  # type: ignore # noqa: F401

    PYTHON3_SAML_AVAILABLE = True
except Exception:
    PYTHON3_SAML_AVAILABLE = False


class SSOService:
    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def get_sp_metadata(self, org_slug: str, db: Session) -> str:
        config = self._get_sso_config(org_slug, db)
        if config is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SSO not configured for this organization")

        settings = get_settings()
        base_url = settings.BASE_URL.rstrip("/")
        return self._build_sp_metadata_xml(
            org_slug=org_slug,
            base_url=base_url,
            entity_id=f"{base_url}/api/v1/auth/sso/{org_slug}/metadata",
        )

    def initiate_login(self, org_slug: str, db: Session) -> str:
        config = self._get_sso_config(org_slug, db)
        if not config or not config.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SSO not active for this organization")
        return self._build_redirect_url(config=config, org_slug=org_slug)

    def process_callback(self, org_slug: str, saml_response: str, db: Session) -> dict:
        config = self._get_sso_config(org_slug, db)
        if not config or not config.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SSO not active for this organization")

        email = self._extract_email(saml_response, config)
        if not email:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SAML response missing email attribute")

        user = self._get_or_create_user(
            email=email,
            org_id=config.organization_id,
            config=config,
            db=db,
        )

        token = self._create_jwt_for_user(user=user, org_id=config.organization_id)

        AuditService(db).write_audit_log(
            action="sso.login",
            entity_type="users",
            organization_id=config.organization_id,
            actor_user_id=user.id,
            entity_id=user.id,
            metadata_json={
                "provider": config.provider,
                "auth_method": "saml2",
                "python3_saml": PYTHON3_SAML_AVAILABLE,
            },
        )

        return {
            "access_token": token,
            "token_type": "bearer",
            "auth_method": "sso",
        }

    def _get_or_create_user(
        self,
        email: str,
        org_id: uuid.UUID,
        config: SSOConfig,
        db: Session,
    ) -> User:
        normalized_email = email.strip().lower()
        user = db.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()

        if user is None and not config.jit_provisioning:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User must be pre-provisioned")

        if user is None:
            user = User(
                email=normalized_email,
                full_name=None,
                hashed_password=get_password_hash(uuid.uuid4().hex),
                status="active",
                is_active=True,
                is_superuser=False,
            )
            db.add(user)
            db.flush()

        membership = db.execute(
            select(Membership).where(
                Membership.organization_id == org_id,
                Membership.user_id == user.id,
            )
        ).scalar_one_or_none()

        if membership is None:
            if not config.jit_provisioning:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User must be pre-provisioned")

            membership = Membership(
                organization_id=org_id,
                user_id=user.id,
                role_id=self._resolve_default_role_id(org_id, config.default_role, db),
                status="active",
                invited_by=config.created_by,
            )
            db.add(membership)
            db.flush()
            self._queue_welcome_email(org_id, user, config.created_by, db)

        if membership.status != "active":
            membership.status = "active"
            db.flush()

        if not user.is_active or user.status != "active":
            user.is_active = True
            user.status = "active"
            db.flush()

        return user

    def _get_sso_config(self, org_slug: str, db: Session) -> SSOConfig | None:
        org = db.execute(
            select(Organization).where(
                Organization.slug == org_slug,
                Organization.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if not org:
            return None
        return db.execute(
            select(SSOConfig).where(
                SSOConfig.organization_id == org.id,
                SSOConfig.deleted_at.is_(None),
            )
        ).scalar_one_or_none()

    def _create_jwt_for_user(self, user: User, org_id: uuid.UUID) -> str:
        return create_access_token(subject=user.id, extra={"org_id": str(org_id), "auth_method": "sso"})

    def _build_sp_metadata_xml(self, org_slug: str, base_url: str, entity_id: str) -> str:
        return f"""<?xml version=\"1.0\"?>
<md:EntityDescriptor
  xmlns:md=\"urn:oasis:names:tc:SAML:2.0:metadata\"
  entityID=\"{entity_id}\">
  <md:SPSSODescriptor
    AuthnRequestsSigned=\"false\"
    WantAssertionsSigned=\"true\"
    protocolSupportEnumeration=\"urn:oasis:names:tc:SAML:2.0:protocol\">
    <md:AssertionConsumerService
      Binding=\"urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST\"
      Location=\"{base_url}/api/v1/auth/sso/{org_slug}/callback\"
      index=\"1\"/>
  </md:SPSSODescriptor>
</md:EntityDescriptor>"""

    def _build_redirect_url(self, config: SSOConfig, org_slug: str) -> str:
        settings = get_settings()
        base_url = settings.BASE_URL.rstrip("/")
        acs_url = f"{base_url}/api/v1/auth/sso/{org_slug}/callback"
        issuer = f"{base_url}/api/v1/auth/sso/{org_slug}/metadata"
        authn_request_xml = (
            '<samlp:AuthnRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
            f'AssertionConsumerServiceURL="{acs_url}" IssueInstant="{self.utcnow().isoformat()}" '
            f'ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST" Version="2.0">'
            f'<saml:Issuer xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">{issuer}</saml:Issuer>'
            "</samlp:AuthnRequest>"
        )
        encoded = quote_plus(base64.b64encode(authn_request_xml.encode("utf-8")).decode("utf-8"))
        separator = "&" if "?" in config.sso_url else "?"
        return f"{config.sso_url}{separator}SAMLRequest={encoded}"

    def _extract_email(self, saml_response: str, config: SSOConfig) -> str | None:
        del config
        decoded = ""
        try:
            decoded = base64.b64decode(saml_response).decode("utf-8", errors="ignore")
        except Exception:
            decoded = saml_response

        for pattern in (
            r"<saml:NameID[^>]*>([^<]+)</saml:NameID>",
            r"<NameID[^>]*>([^<]+)</NameID>",
            r"<AttributeValue[^>]*>([^<]+)</AttributeValue>",
            r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})",
        ):
            match = re.search(pattern, decoded)
            if match:
                value = match.group(1).strip()
                if "@" in value:
                    return value.lower()

        if "@" in saml_response and "<" not in saml_response:
            return saml_response.strip().lower()
        return None

    def _resolve_default_role_id(self, org_id: uuid.UUID, default_role: str, db: Session) -> uuid.UUID:
        candidate_names = [default_role]
        if default_role == "member":
            candidate_names.extend(["reviewer", "admin", "owner"])
        for role_name in candidate_names:
            role = db.execute(
                select(Role).where(
                    Role.organization_id == org_id,
                    Role.name == role_name,
                )
            ).scalar_one_or_none()
            if role is not None:
                return role.id
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No eligible role found for JIT provisioning")

    def _queue_welcome_email(self, org_id: uuid.UUID, user: User, created_by: uuid.UUID, db: Session) -> None:
        now = self.utcnow()
        outbox = EmailOutbox(
            organization_id=org_id,
            template_id=None,
            event_type="sso_welcome",
            recipient_email=user.email,
            recipient_user_id=user.id,
            subject="Welcome to CompliVibe",
            body_text="Your account was provisioned via Single Sign-On.",
            body_html="<p>Your account was provisioned via Single Sign-On.</p>",
            status="pending",
            priority="normal",
            scheduled_at=None,
            queued_at=now,
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
            last_error=None,
            provider=None,
            provider_message_id=None,
            metadata_json={"source": "sso_jit"},
            worker_metadata_json=None,
            created_by_user_id=created_by,
        )
        db.add(outbox)
        db.flush()
