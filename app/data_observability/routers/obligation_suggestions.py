import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.data_observability.schemas.data_obligations import DataObligationSuggestionPersistedRead
from app.data_observability.services.data_obligation_service import DataObligationService
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/data-observability/obligation-suggestions", tags=["data-observability-obligation-suggestions"])


@router.get("", response_model=list[DataObligationSuggestionPersistedRead])
def list_data_obligation_suggestions(
    data_asset_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:read")),
) -> list[DataObligationSuggestionPersistedRead]:
    service = DataObligationService(db)
    rows = service.list_suggestions(
        organization.id,
        data_asset_id=data_asset_id,
        status=status,
        page=page,
        page_size=page_size,
    )
    return [DataObligationSuggestionPersistedRead.model_validate(service.suggestion_payload(row)) for row in rows]


@router.post("/{suggestion_id}/apply", response_model=DataObligationSuggestionPersistedRead)
def apply_data_obligation_suggestion(
    suggestion_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataObligationSuggestionPersistedRead:
    service = DataObligationService(db)
    row = service.apply_suggestion(organization.id, suggestion_id, current_user.id)
    db.commit()
    return DataObligationSuggestionPersistedRead.model_validate(service.suggestion_payload(row))


@router.post("/{suggestion_id}/dismiss", response_model=DataObligationSuggestionPersistedRead)
def dismiss_data_obligation_suggestion(
    suggestion_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("data:write")),
) -> DataObligationSuggestionPersistedRead:
    service = DataObligationService(db)
    row = service.dismiss_suggestion(organization.id, suggestion_id, current_user.id)
    db.commit()
    return DataObligationSuggestionPersistedRead.model_validate(service.suggestion_payload(row))
