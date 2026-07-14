import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_organization, get_db, require_permission
from app.models.audit_log import AuditLog
from app.models.membership import Membership
from app.models.organization import Organization
from app.schemas.audit_log import AuditLogRead

router = APIRouter(prefix="/audit-logs", tags=["audit_logs"])


@router.get("", response_model=list[AuditLogRead])
def list_audit_logs(
    entity_id: uuid.UUID | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit_logs:read")),
) -> list[AuditLogRead]:
    stmt = select(AuditLog).where(AuditLog.organization_id == organization.id)
    if entity_id is not None:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if entity_type is not None:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    stmt = stmt.order_by(AuditLog.created_at.desc()).limit(200)
    logs = db.execute(stmt).scalars().all()
    return [AuditLogRead.model_validate(log) for log in logs]
