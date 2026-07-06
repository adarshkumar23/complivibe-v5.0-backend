from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import quote_plus

from fastapi import Request
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, get_password_hash
from app.models.email_outbox import EmailOutbox
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.role import Role
from app.models.saml_assertion_replay import SAMLAssertionReplay
from app.models.sso_config import SSOConfig
from app.models.user import User
from app.services.audit_service import AuditService

try:
    from onelogin.saml2.auth import OneLogin_Saml2_Auth  # type: ignore
    from onelogin.saml2.constants import OneLogin_Saml2_Constants  # type: ignore

    PYTHON3_SAML_AVAILABLE = True
except Exception:
    PYTHON3_SAML_AVAILABLE = False


class SAMLValidationFailure(Exception):
    def __init__(self, validation_check: str, reason: str) -> None:
        super().__init__(reason)
        self.validation_check = validation_check
        self.reason = reason


class SSOService:
    REPLAY_FALLBACK_TTL_MINUTES = 10

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

    def process_callback(self, org_slug: str, saml_response: str, request: Request, db: Session) -> dict:
        config = self._get_sso_config(org_slug, db)
        if not config or not config.is_active:
            if config is not None:
                self._audit_login_failure(
                    db,
                    config=config,
                    request=request,
                    validation_check="configuration",
                    reason="SSO not active for this organization",
                )
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SSO not active for this organization")

        try:
            auth = self._validate_saml_response(config=config, org_slug=org_slug, saml_response=saml_response, request=request)
            assertion_id = auth.get_last_assertion_id()
            if not assertion_id:
                raise SAMLValidationFailure("assertion_id", "Validated SAML response did not include an assertion ID")
            email = self._extract_verified_email(auth, config)
            if not email:
                raise SAMLValidationFailure("nameid_or_attribute", "Validated SAML response missing configured email claim")
            self._consume_assertion_id(db, config=config, assertion_id=assertion_id, name_id=email, auth=auth)
        except SAMLValidationFailure as exc:
            self._audit_login_failure(
                db,
                config=config,
                request=request,
                validation_check=exc.validation_check,
                reason=exc.reason,
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid SAML response") from exc

        try:
            user = self._get_or_create_user(
                email=email,
                org_id=config.organization_id,
                config=config,
                db=db,
            )
        except HTTPException as exc:
            self._audit_login_failure(
                db,
                config=config,
                request=request,
                validation_check="user_provisioning",
                reason=str(exc.detail),
            )
            raise

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
                "assertion_id": assertion_id,
            },
            ip_address=self._request_ip(request),
            user_agent=request.headers.get("User-Agent"),
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

    def _validate_saml_response(
        self,
        *,
        config: SSOConfig,
        org_slug: str,
        saml_response: str,
        request: Request,
    ):
        if not PYTHON3_SAML_AVAILABLE:
            raise SAMLValidationFailure("library", "python3-saml is not available")

        request_data = self._build_saml_request_data(request, saml_response)
        try:
            auth = OneLogin_Saml2_Auth(request_data, old_settings=self._build_saml_settings(config, org_slug, request))
            auth.process_response()
        except Exception as exc:
            reason = str(exc)
            raise SAMLValidationFailure(self._classify_validation_failure(reason), reason) from exc
        if auth.get_errors() or not auth.is_authenticated():
            reason = auth.get_last_error_reason() or ",".join(auth.get_errors()) or "SAML response validation failed"
            raise SAMLValidationFailure(self._classify_validation_failure(reason), reason)
        return auth

    def _build_saml_request_data(self, request: Request, saml_response: str) -> dict:
        scheme = request.url.scheme or "http"
        host = request.headers.get("host") or request.url.netloc
        port = request.url.port or (443 if scheme == "https" else 80)
        return {
            "https": "on" if scheme == "https" else "off",
            "http_host": host,
            "server_port": port,
            "script_name": "",
            "path_info": request.url.path,
            "get_data": dict(request.query_params),
            "post_data": {"SAMLResponse": saml_response},
        }

    def _build_saml_settings(self, config: SSOConfig, org_slug: str, request: Request) -> dict:
        base_url = f"{request.url.scheme}://{request.headers.get('host') or request.url.netloc}".rstrip("/")
        acs_url = f"{base_url}/api/v1/auth/sso/{org_slug}/callback"
        sp_entity_id = f"{base_url}/api/v1/auth/sso/{org_slug}/metadata"
        idp_cert = config.certificate.strip()
        return {
            "strict": True,
            "debug": False,
            "sp": {
                "entityId": sp_entity_id,
                "assertionConsumerService": {
                    "url": acs_url,
                    "binding": OneLogin_Saml2_Constants.BINDING_HTTP_POST,
                },
                "NameIDFormat": OneLogin_Saml2_Constants.NAMEID_EMAIL_ADDRESS,
            },
            "idp": {
                "entityId": config.entity_id,
                "singleSignOnService": {
                    "url": config.sso_url,
                    "binding": OneLogin_Saml2_Constants.BINDING_HTTP_REDIRECT,
                },
                "singleLogoutService": {
                    "url": config.slo_url or config.sso_url,
                    "binding": OneLogin_Saml2_Constants.BINDING_HTTP_REDIRECT,
                },
                "x509cert": idp_cert,
            },
            "security": {
                "authnRequestsSigned": False,
                "wantAssertionsSigned": True,
                "wantMessagesSigned": False,
                "wantNameId": True,
                "wantAssertionsEncrypted": False,
                "wantNameIdEncrypted": False,
                "wantAttributeStatement": False,
                "requestedAuthnContext": False,
                "failOnAuthnContextMismatch": False,
                "rejectDeprecatedAlgorithm": True,
                "signatureAlgorithm": OneLogin_Saml2_Constants.RSA_SHA256,
                "digestAlgorithm": OneLogin_Saml2_Constants.SHA256,
            },
        }

    def _extract_verified_email(self, auth, config: SSOConfig) -> str | None:
        mapping = config.attribute_mapping or {}
        email_claim = str(mapping.get("email") or "NameID")
        if email_claim.lower() == "nameid":
            candidate = auth.get_nameid()
            return self._normalize_email(candidate)

        attributes = auth.get_attributes() or {}
        values = attributes.get(email_claim) or attributes.get(email_claim.lower()) or attributes.get(email_claim.upper())
        if isinstance(values, list) and values:
            return self._normalize_email(str(values[0]))
        if isinstance(values, str):
            return self._normalize_email(values)
        return None

    @staticmethod
    def _normalize_email(value: str | None) -> str | None:
        if not value:
            return None
        normalized = value.strip().lower()
        if "@" not in normalized:
            return None
        return normalized

    def _consume_assertion_id(self, db: Session, *, config: SSOConfig, assertion_id: str, name_id: str, auth) -> None:
        existing = db.execute(
            select(SAMLAssertionReplay).where(
                SAMLAssertionReplay.organization_id == config.organization_id,
                SAMLAssertionReplay.assertion_id == assertion_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise SAMLValidationFailure("replay", "SAML assertion ID has already been consumed")

        expires_at = self._assertion_expiry(auth)
        db.add(
            SAMLAssertionReplay(
                organization_id=config.organization_id,
                sso_config_id=config.id,
                assertion_id=assertion_id,
                name_id=name_id,
                expires_at=expires_at,
            )
        )
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise SAMLValidationFailure("replay", "SAML assertion ID has already been consumed") from exc

    def _assertion_expiry(self, auth) -> datetime:
        expires = auth.get_last_assertion_not_on_or_after() or auth.get_session_expiration()
        if isinstance(expires, (int, float)) and expires > 0:
            return datetime.fromtimestamp(float(expires), tz=UTC)
        if isinstance(expires, datetime):
            return expires if expires.tzinfo is not None else expires.replace(tzinfo=UTC)
        return self.utcnow() + timedelta(minutes=self.REPLAY_FALLBACK_TTL_MINUTES)

    def _audit_login_failure(
        self,
        db: Session,
        *,
        config: SSOConfig,
        request: Request,
        validation_check: str,
        reason: str,
    ) -> None:
        AuditService(db).write_audit_log(
            action="sso.login_failed",
            entity_type="users",
            organization_id=config.organization_id,
            entity_id=config.id,
            metadata_json={
                "provider": config.provider,
                "auth_method": "saml2",
                "validation_check": validation_check,
                "reason": reason,
            },
            ip_address=self._request_ip(request),
            user_agent=request.headers.get("User-Agent"),
        )
        db.commit()

    @staticmethod
    def _request_ip(request: Request) -> str | None:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",", 1)[0].strip()
        return request.client.host if request.client else None

    @staticmethod
    def _classify_validation_failure(reason: str) -> str:
        normalized = reason.lower()
        checks = {
            "signature": ("signature", "signed"),
            "issuer": ("issuer",),
            "audience": ("audience",),
            "destination": ("destination", "recipient"),
            "timestamp": ("timestamp", "expired", "not yet valid", "notonorafter", "notbefore"),
            "subject_confirmation": ("subjectconfirmation",),
        }
        for check, needles in checks.items():
            if any(needle in normalized for needle in needles):
                return check
        return "saml_response"

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
