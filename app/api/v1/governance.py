import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.organization import Organization
from app.models.retention_policy import RetentionPolicy
from app.models.user import User
from app.repositories.retention_repository import RetentionRepository
from app.schemas.exports import (
    GovernanceRetentionSummary,
    RetentionEvaluateRequest,
    RetentionEvaluateResponse,
    RetentionPolicyCreate,
    RetentionPolicyRead,
    RetentionPolicyUpdate,
)
from app.services.audit_service import AuditService
from app.services.retention_service import RetentionService

router = APIRouter(prefix="/governance", tags=["governance"])


def _policy_read(row: RetentionPolicy) -> RetentionPolicyRead:
    return RetentionPolicyRead(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        description=row.description,
        entity_type=row.entity_type,
        retention_days=row.retention_days,
        lock_days=row.lock_days,
        legal_hold_default=row.legal_hold_default,
        status=row.status,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/retention/policies", response_model=RetentionPolicyRead, status_code=status.HTTP_201_CREATED)
def create_retention_policy(
    payload: RetentionPolicyCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("retention:write")),
) -> RetentionPolicyRead:
    service = RetentionService(db)
    service.validate_entity_type(payload.entity_type)
    row = RetentionPolicy(
        organization_id=organization.id,
        name=payload.name,
        description=payload.description,
        entity_type=payload.entity_type,
        retention_days=payload.retention_days,
        lock_days=payload.lock_days,
        legal_hold_default=payload.legal_hold_default,
        status=payload.status,
        created_by_user_id=current_user.id,
    )
    db.add(row)
    db.flush()
    AuditService(db).write_audit_log(
        action="retention_policy.created",
        entity_type="retention_policy",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"entity_type": row.entity_type, "retention_days": row.retention_days, "lock_days": row.lock_days},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _policy_read(row)


@router.get("/retention/policies", response_model=list[RetentionPolicyRead])
def list_retention_policies(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("retention:read")),
) -> list[RetentionPolicyRead]:
    rows = RetentionRepository(db).list_policies(organization.id)
    return [_policy_read(row) for row in rows]


@router.patch("/retention/policies/{policy_id}", response_model=RetentionPolicyRead)
def update_retention_policy(
    policy_id: uuid.UUID,
    payload: RetentionPolicyUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("retention:write")),
) -> RetentionPolicyRead:
    service = RetentionService(db)
    row = service.require_policy(organization.id, policy_id)
    if payload.entity_type is not None:
        service.validate_entity_type(payload.entity_type)
    before = {
        "name": row.name,
        "entity_type": row.entity_type,
        "retention_days": row.retention_days,
        "lock_days": row.lock_days,
        "legal_hold_default": row.legal_hold_default,
        "status": row.status,
    }
    for field in ["name", "description", "entity_type", "retention_days", "lock_days", "legal_hold_default", "status"]:
        value = getattr(payload, field)
        if value is not None:
            setattr(row, field, value)
    db.flush()
    AuditService(db).write_audit_log(
        action="retention_policy.updated",
        entity_type="retention_policy",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "name": row.name,
            "entity_type": row.entity_type,
            "retention_days": row.retention_days,
            "lock_days": row.lock_days,
            "legal_hold_default": row.legal_hold_default,
            "status": row.status,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _policy_read(row)


@router.post("/retention/policies/{policy_id}/archive", response_model=RetentionPolicyRead)
def archive_retention_policy(
    policy_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("retention:write")),
) -> RetentionPolicyRead:
    service = RetentionService(db)
    row = service.require_policy(organization.id, policy_id)
    before = row.status
    row.status = "archived"
    db.flush()
    AuditService(db).write_audit_log(
        action="retention_policy.archived",
        entity_type="retention_policy",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json={"status": before},
        after_json={"status": row.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _policy_read(row)


@router.post("/retention/evaluate", response_model=RetentionEvaluateResponse)
def evaluate_retention(
    payload: RetentionEvaluateRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("retention:read")),
) -> RetentionEvaluateResponse:
    if not payload.dry_run:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only dry_run=true is supported in this phase")
    if payload.entity_type is not None:
        RetentionService.validate_entity_type(payload.entity_type)
    result = RetentionService(db).evaluate(organization_id=organization.id, entity_type=payload.entity_type)
    return RetentionEvaluateResponse(dry_run=True, **result)


@router.get("/retention/summary", response_model=GovernanceRetentionSummary)
def retention_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _=Depends(require_permission("retention:read")),
) -> GovernanceRetentionSummary:
    return GovernanceRetentionSummary(**RetentionService(db).summary(organization_id=organization.id))
