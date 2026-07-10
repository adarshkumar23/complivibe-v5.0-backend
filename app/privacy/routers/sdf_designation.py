from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.privacy.schemas.sdf_designation import SDFConfirmRequest, SDFConfirmResult, SDFSuggestionRead
from app.privacy.services.sdf_designation_service import SDFDesignationService

router = APIRouter(prefix="/privacy/sdf-designation", tags=["privacy-sdf-designation"])


@router.post("/suggest", response_model=SDFSuggestionRead, status_code=201)
def suggest_sdf_designation(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("privacy:read")),
) -> SDFSuggestionRead:
    row = SDFDesignationService(db).suggest_sdf_designation(organization.id)
    db.commit()
    db.refresh(row)
    return SDFSuggestionRead.model_validate(row)


@router.post("/confirm", response_model=SDFConfirmResult)
def confirm_sdf_designation(
    payload: SDFConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("org:update")),
) -> SDFConfirmResult:
    result = SDFDesignationService(db).confirm_sdf_designation(
        organization.id,
        confirmed_value=payload.confirmed_value,
        sdf_category=payload.sdf_category,
        actor_user_id=current_user.id,
    )
    db.commit()
    return SDFConfirmResult(**result)
