from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.org_email_config import OrgEmailConfig
from app.models.organization import Organization
from app.models.role import Role
from app.models.user import User
from app.platform.schemas.email_config import (
    EmailConfigResponse,
    EmailConfigTestResponse,
    EmailConfigUpsertRequest,
    EmailSenderVerificationResponse,
)
from app.platform.services.ses_service import SESService
from app.privacy.services.email_config_service import EmailConfigService
from app.services.audit_service import AuditService

router = APIRouter(prefix="/email-config", tags=["email-config"])


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _require_admin_membership(db: Session, membership: Membership) -> None:
    role = db.execute(select(Role).where(Role.id == membership.role_id)).scalar_one_or_none()
    if role is None or role.name not in {"owner", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Org admin role required")


def _serialize(row: OrgEmailConfig | None, org_id) -> EmailConfigResponse:
    if row is None:
        return EmailConfigResponse(
            id=None,
            organization_id=org_id,
            use_platform_ses=True,
            aws_region="ap-south-1",
            from_email=None,
            from_name=None,
            reply_to_email=None,
            is_active=False,
            sent_today=0,
            daily_send_limit=1000,
            created_at=None,
            updated_at=None,
        )

    return EmailConfigResponse(
        id=row.id,
        organization_id=row.organization_id,
        use_platform_ses=bool(getattr(row, "use_platform_ses", True)),
        aws_region=row.aws_region,
        from_email=row.from_email,
        from_name=row.from_name,
        reply_to_email=row.reply_to_email,
        is_active=row.is_active,
        sent_today=int(getattr(row, "sent_today", 0) or 0),
        daily_send_limit=int(getattr(row, "daily_send_limit", 1000) or 1000),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("", response_model=EmailConfigResponse)
def upsert_email_config(
    payload: EmailConfigUpsertRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("email:admin")),
) -> EmailConfigResponse:
    _require_admin_membership(db, membership)
    service = SESService()

    if not payload.use_platform_ses:
        if not payload.aws_access_key_id or not payload.aws_secret_access_key or not payload.from_email:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Custom SES requires aws_access_key_id, aws_secret_access_key, and from_email",
            )
        verification = service.verify_credentials(
            access_key_id=payload.aws_access_key_id,
            secret_access_key=payload.aws_secret_access_key,
            region=payload.aws_region or "ap-south-1",
            from_email=str(payload.from_email),
        )
        if not verification.get("valid"):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=verification.get("error", "Invalid SES credentials"))

    row = db.execute(select(OrgEmailConfig).where(OrgEmailConfig.organization_id == organization.id)).scalar_one_or_none()
    now = _utcnow()

    if row is None:
        row = OrgEmailConfig(
            organization_id=organization.id,
            provider="ses",
            config_json="{}",
            created_by=current_user.id,
            created_at=now,
            updated_at=now,
            is_active=True,
        )
        db.add(row)

    row.use_platform_ses = payload.use_platform_ses
    row.aws_region = payload.aws_region or "ap-south-1"
    row.from_email = str(payload.from_email) if payload.from_email else row.from_email
    row.from_name = payload.from_name
    row.reply_to_email = str(payload.reply_to_email) if payload.reply_to_email else None
    row.daily_send_limit = payload.daily_send_limit
    row.is_active = True
    row.updated_at = now

    if payload.use_platform_ses:
        row.aws_access_key_id_enc = None
        row.aws_secret_key_enc = None
        row.config_json = "{}"
    else:
        assert payload.aws_access_key_id is not None
        assert payload.aws_secret_access_key is not None
        assert payload.from_email is not None
        row.aws_access_key_id_enc = service.encrypt_credential(payload.aws_access_key_id)
        row.aws_secret_key_enc = service.encrypt_credential(payload.aws_secret_access_key)
        # Keep legacy field populated for existing services still reading config_json.
        row.config_json = EmailConfigService.encrypt_config(
            {
                "aws_access_key_id": payload.aws_access_key_id,
                "aws_secret_access_key": payload.aws_secret_access_key,
                "region": row.aws_region,
                "from_address": str(payload.from_email),
            }
        )

    db.flush()
    AuditService(db).write_audit_log(
        action="org_email_config.updated",
        entity_type="org_email_configs",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        metadata_json={
            "use_platform_ses": row.use_platform_ses,
            "is_active": row.is_active,
            "from_email": row.from_email,
        },
    )
    db.commit()
    db.refresh(row)
    return _serialize(row, organization.id)


@router.get("", response_model=EmailConfigResponse)
def get_email_config(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("email:admin")),
) -> EmailConfigResponse:
    _require_admin_membership(db, membership)
    row = db.execute(select(OrgEmailConfig).where(OrgEmailConfig.organization_id == organization.id)).scalar_one_or_none()
    return _serialize(row, organization.id)


@router.post("/test", response_model=EmailConfigTestResponse)
def send_test_email(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("email:admin")),
) -> EmailConfigTestResponse:
    _require_admin_membership(db, membership)
    if not current_user.email:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Admin email is required")

    result = SESService().send_email(
        to_email=current_user.email,
        subject="CompliVibe SES configuration test",
        html_body="<p>This is a CompliVibe SES configuration test email.</p>",
        text_body="This is a CompliVibe SES configuration test email.",
        org_id=organization.id,
        db=db,
    )
    if not result["success"]:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result["error"])

    row = db.execute(select(OrgEmailConfig).where(OrgEmailConfig.organization_id == organization.id)).scalar_one_or_none()
    if row is not None:
        row.test_sent_at = _utcnow()
        row.updated_at = row.test_sent_at
        db.flush()

    AuditService(db).write_audit_log(
        action="org_email_config.test_sent",
        entity_type="org_email_configs",
        organization_id=organization.id,
        actor_user_id=current_user.id,
        entity_id=row.id if row else None,
        metadata_json={"sent_to": current_user.email},
    )
    db.commit()
    return EmailConfigTestResponse(success=True, message_id=result.get("message_id"), sent_to=current_user.email)


@router.delete("", response_model=EmailConfigResponse)
def deactivate_email_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("email:admin")),
) -> EmailConfigResponse:
    _require_admin_membership(db, membership)
    row = db.execute(select(OrgEmailConfig).where(OrgEmailConfig.organization_id == organization.id)).scalar_one_or_none()
    if row is None:
        return _serialize(None, organization.id)

    row.is_active = False
    row.use_platform_ses = True
    row.updated_at = _utcnow()
    db.flush()

    AuditService(db).write_audit_log(
        action="org_email_config.deactivated",
        entity_type="org_email_configs",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _serialize(row, organization.id)


@router.get("/verify-sender", response_model=EmailSenderVerificationResponse)
def verify_sender(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("email:admin")),
) -> EmailSenderVerificationResponse:
    _require_admin_membership(db, membership)
    row = db.execute(select(OrgEmailConfig).where(OrgEmailConfig.organization_id == organization.id)).scalar_one_or_none()
    ses = SESService()

    if row is not None and not row.use_platform_ses and row.aws_access_key_id_enc and row.aws_secret_key_enc and row.from_email:
        access_key = ses.decrypt_credential(row.aws_access_key_id_enc)
        secret_key = ses.decrypt_credential(row.aws_secret_key_enc)
        result = ses.verify_credentials(
            access_key_id=access_key,
            secret_access_key=secret_key,
            region=row.aws_region or "ap-south-1",
            from_email=row.from_email,
        )
        return EmailSenderVerificationResponse(**result)

    settings = get_settings()
    if not settings.AWS_SES_FROM_EMAIL:
        return EmailSenderVerificationResponse(valid=False, error="Platform sender email is not configured")

    result = ses.verify_credentials(
        access_key_id=settings.AWS_SES_ACCESS_KEY_ID,
        secret_access_key=settings.AWS_SES_SECRET_ACCESS_KEY,
        region=settings.AWS_SES_REGION,
        from_email=settings.AWS_SES_FROM_EMAIL,
    )
    return EmailSenderVerificationResponse(**result)
