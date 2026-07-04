import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai_governance.schemas.iso42001_nist_rmf import (
    ISO42001SummaryRead,
    ISO42001TrackerRead,
    ISO42001TrackerUpdateRequest,
)
from app.ai_governance.services.iso42001_service import ISO42001Service
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/ai-governance/iso42001", tags=["ai-governance-iso42001"])


@router.get("/conformity-tracker", response_model=list[ISO42001TrackerRead])
def get_conformity_tracker(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> list[ISO42001TrackerRead]:
    rows = ISO42001Service(db).get_or_create_trackers(organization.id)
    db.commit()
    return [ISO42001TrackerRead.model_validate(row) for row in rows]


@router.post("/conformity-tracker/{clause_ref}/update", response_model=ISO42001TrackerRead)
def update_conformity_tracker(
    clause_ref: str,
    payload: ISO42001TrackerUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> ISO42001TrackerRead:
    row = ISO42001Service(db).update_tracker(
        organization.id,
        clause_ref,
        payload.status,
        payload.notes,
        payload.evidence_id,
        current_user.id,
        fields_set=payload.model_fields_set,
    )
    db.commit()
    db.refresh(row)
    return ISO42001TrackerRead.model_validate(row)


@router.get("/summary", response_model=ISO42001SummaryRead)
def get_conformity_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> ISO42001SummaryRead:
    payload = ISO42001Service(db).get_conformity_summary(organization.id)
    db.commit()
    return ISO42001SummaryRead(**payload)
