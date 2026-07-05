import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.training_completion_record import TrainingCompletionRecord
from app.models.user import User
from app.schemas.training_analytics import (
    TrainingAnalyticsSummaryResponse,
    TrainingCompletionRecordComplete,
    TrainingCompletionRecordCreate,
    TrainingCompletionRecordResponse,
)
from app.services.training_analytics_service import TrainingAnalyticsService

router = APIRouter(prefix="/training-analytics", tags=["training-analytics"])


def _comparable(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def _read(row: TrainingCompletionRecord) -> TrainingCompletionRecordResponse:
    now = _comparable(datetime.now(UTC))
    is_overdue = row.completed_at is None and _comparable(row.due_date) < now
    return TrainingCompletionRecordResponse(
        **TrainingCompletionRecordResponse.model_validate(row).model_dump(exclude={"is_overdue"}),
        is_overdue=is_overdue,
    )


@router.post("/records", response_model=TrainingCompletionRecordResponse, status_code=status.HTTP_201_CREATED)
def create_training_record(
    payload: TrainingCompletionRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("training_analytics:write")),
) -> TrainingCompletionRecordResponse:
    row = TrainingAnalyticsService(db).create_record(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _read(row)


@router.get("/records", response_model=list[TrainingCompletionRecordResponse])
def list_training_records(
    business_unit_id: uuid.UUID | None = Query(default=None),
    training_type: str | None = Query(default=None),
    completed: bool | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("training_analytics:read")),
) -> list[TrainingCompletionRecordResponse]:
    rows = TrainingAnalyticsService(db).list_records(
        organization.id,
        business_unit_id=business_unit_id,
        training_type=training_type,
        completed=completed,
        skip=skip,
        limit=limit,
    )
    return [_read(row) for row in rows]


@router.patch("/records/{record_id}", response_model=TrainingCompletionRecordResponse)
def complete_training_record(
    record_id: uuid.UUID,
    payload: TrainingCompletionRecordComplete,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("training_analytics:write")),
) -> TrainingCompletionRecordResponse:
    row = TrainingAnalyticsService(db).complete_record(organization.id, record_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _read(row)


@router.get("/summary", response_model=TrainingAnalyticsSummaryResponse)
def get_training_analytics_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("training_analytics:read")),
) -> TrainingAnalyticsSummaryResponse:
    return TrainingAnalyticsService(db).get_summary(organization.id)
