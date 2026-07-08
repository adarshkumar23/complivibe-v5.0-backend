import uuid

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.schemas.digest import DigestConfigRead, DigestDailyUpdate, DigestWeeklyUpdate
from app.compliance.services.digest_service import DigestService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/preferences/digest", tags=["digest-preferences"])


@router.get("", response_model=list[DigestConfigRead])
def get_digest_configs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> list[DigestConfigRead]:
    rows = DigestService(db).get_or_create_configs(organization.id, current_user.id)
    return [
        DigestConfigRead(
            id=str(row.id),
            organization_id=str(row.organization_id),
            user_id=str(row.user_id),
            digest_type=row.digest_type,
            is_enabled=bool(row.is_enabled),
            send_time_utc=row.send_time_utc,
            send_day_of_week=row.send_day_of_week,
            last_sent_at=row.last_sent_at,
        )
        for row in rows
    ]


@router.put("/daily", response_model=DigestConfigRead)
def update_daily_digest(
    payload: DigestDailyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> DigestConfigRead:
    row = DigestService(db).update_daily_config(organization.id, current_user.id, payload.is_enabled, payload.send_time_utc)
    db.commit()
    db.refresh(row)
    return DigestConfigRead(
        id=str(row.id),
        organization_id=str(row.organization_id),
        user_id=str(row.user_id),
        digest_type=row.digest_type,
        is_enabled=bool(row.is_enabled),
        send_time_utc=row.send_time_utc,
        send_day_of_week=row.send_day_of_week,
        last_sent_at=row.last_sent_at,
    )


@router.put("/weekly", response_model=DigestConfigRead)
def update_weekly_digest(
    payload: DigestWeeklyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> DigestConfigRead:
    row = DigestService(db).update_weekly_config(organization.id, current_user.id, payload.is_enabled, payload.send_day_of_week)
    db.commit()
    db.refresh(row)
    return DigestConfigRead(
        id=str(row.id),
        organization_id=str(row.organization_id),
        user_id=str(row.user_id),
        digest_type=row.digest_type,
        is_enabled=bool(row.is_enabled),
        send_time_utc=row.send_time_utc,
        send_day_of_week=row.send_day_of_week,
        last_sent_at=row.last_sent_at,
    )


@router.post("/send-now/{digest_type}")
def send_digest_now(
    digest_type: str = Path(..., pattern="^(daily|weekly)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("email:admin")),
) -> dict:
    if digest_type not in {"daily", "weekly"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid digest type")
    queued = DigestService(db).send_digest(organization.id, current_user.id, digest_type, db)
    db.commit()
    return {"queued": bool(queued), "digest_type": digest_type}


@router.get("/preview/{digest_type}")
def preview_digest(
    digest_type: str = Path(..., pattern="^(daily|weekly)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("org:read")),
) -> dict:
    """Return the digest content that would be sent, without queuing an email.

    Lets the UI show "here's what your next digest looks like" without side effects,
    matching the read-only preview pattern used elsewhere in the platform.
    """
    if digest_type not in {"daily", "weekly"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid digest type")
    service = DigestService(db)
    if digest_type == "daily":
        content = service._with_digest_narrative(
            org_id=organization.id,
            user_id=current_user.id,
            payload=service.build_daily_digest(organization.id, current_user.id, db),
        )
    else:
        content = service.build_weekly_digest(organization.id, current_user.id, db)
    db.rollback()
    return content
