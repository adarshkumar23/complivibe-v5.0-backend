from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.privacy.schemas.email_config import (
    OrgEmailConfigStatusRead,
    OrgEmailConfigTestRequest,
    OrgEmailConfigTestResponse,
    OrgEmailConfigUpsertRequest,
)
from app.privacy.services.email_config_service import EmailConfigService

router = APIRouter(prefix="/admin/email-config", tags=["admin-email-config"])


@router.post("", response_model=OrgEmailConfigStatusRead)
def upsert_email_config(
    payload: OrgEmailConfigUpsertRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("email:admin")),
) -> OrgEmailConfigStatusRead:
    row = EmailConfigService(db).upsert_config(organization.id, payload, current_user.id, membership)
    db.commit()
    db.refresh(row)
    return OrgEmailConfigStatusRead(
        id=row.id,
        organization_id=row.organization_id,
        provider=row.provider,
        is_active=row.is_active,
        test_sent_at=row.test_sent_at,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        config_configured=True,
    )


@router.get("", response_model=OrgEmailConfigStatusRead)
def get_email_config_status(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("email:admin")),
) -> OrgEmailConfigStatusRead:
    EmailConfigService(db)._require_admin_membership(membership)
    row = EmailConfigService(db).get_config(organization.id)
    if row is None:
        return OrgEmailConfigStatusRead(
            id=None,
            organization_id=organization.id,
            provider="ses",
            is_active=False,
            test_sent_at=None,
            created_by=None,
            created_at=None,
            updated_at=None,
            config_configured=False,
        )
    return OrgEmailConfigStatusRead(
        id=row.id,
        organization_id=row.organization_id,
        provider=row.provider,
        is_active=row.is_active,
        test_sent_at=row.test_sent_at,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        config_configured=True,
    )


@router.post("/test", response_model=OrgEmailConfigTestResponse)
def send_test_email(
    payload: OrgEmailConfigTestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("email:admin")),
) -> OrgEmailConfigTestResponse:
    ok, sent_to = EmailConfigService(db).send_test_email(
        organization.id,
        membership,
        actor_user_id=current_user.id,
        to_address=str(payload.to_address) if payload.to_address else None,
    )
    db.commit()
    return OrgEmailConfigTestResponse(success=ok, sent_to=sent_to)
