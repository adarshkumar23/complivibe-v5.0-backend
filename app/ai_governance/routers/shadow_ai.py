import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.ai_governance.schemas.ai_systems import AISystemCreate, AISystemRead
from app.ai_governance.schemas.shadow_ai import ShadowAIDetectionRead, ShadowAIDismissRequest, ShadowAIReportCreate
from app.ai_governance.services.shadow_ai_service import ShadowAIService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/ai-governance/shadow-ai", tags=["ai-governance-shadow-ai"])


@router.post("/report", response_model=ShadowAIDetectionRead, status_code=status.HTTP_201_CREATED)
def report_detection(
    payload: ShadowAIReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> ShadowAIDetectionRead:
    row = ShadowAIService(db).report_detection(
        organization.id,
        detected_name=payload.detected_name,
        detection_method="manual_report",
        confidence="medium",
        reported_by=current_user.id,
        notes=payload.notes,
    )
    db.commit()
    db.refresh(row)
    return ShadowAIDetectionRead.from_row(row)


@router.get("/detections", response_model=list[ShadowAIDetectionRead])
def list_detections(
    status_value: str | None = Query(default=None, alias="status"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[ShadowAIDetectionRead]:
    rows = ShadowAIService(db).list_detections(
        organization.id, status_value=status_value, skip=skip, limit=limit
    )
    return [ShadowAIDetectionRead.from_row(row) for row in rows]


@router.get("/detections/{detection_id}", response_model=ShadowAIDetectionRead)
def get_detection(
    detection_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> ShadowAIDetectionRead:
    row = ShadowAIService(db).get_detection(organization.id, detection_id)
    return ShadowAIDetectionRead.from_row(row)


@router.post("/detections/{detection_id}/review", response_model=ShadowAIDetectionRead)
def review_detection(
    detection_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> ShadowAIDetectionRead:
    row = ShadowAIService(db).review_detection(organization.id, detection_id, current_user.id)
    db.commit()
    db.refresh(row)
    return ShadowAIDetectionRead.from_row(row)


@router.post("/detections/{detection_id}/register", response_model=AISystemRead, status_code=status.HTTP_201_CREATED)
def register_detection(
    detection_id: uuid.UUID,
    payload: AISystemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRead:
    row = ShadowAIService(db).register_as_system(organization.id, detection_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return AISystemRead.model_validate(row)


@router.post("/detections/{detection_id}/dismiss", response_model=ShadowAIDetectionRead)
def dismiss_detection(
    detection_id: uuid.UUID,
    payload: ShadowAIDismissRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> ShadowAIDetectionRead:
    row = ShadowAIService(db).dismiss_detection(organization.id, detection_id, current_user.id, notes=payload.notes)
    db.commit()
    db.refresh(row)
    return ShadowAIDetectionRead.from_row(row)
