from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.compliance.services.risk_dependency_service import RiskDependencyService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.risk_dependency import RiskDependency
from app.models.user import User
from app.schemas.risk_dependency import (
    RiskDependencyCreate,
    RiskDependencyGraph,
    RiskDependencyRead,
)
from app.services.audit_service import AuditService

router = APIRouter(prefix="/risks", tags=["risk-dependencies"])


def _dependency_read(dependency: RiskDependency) -> RiskDependencyRead:
    return RiskDependencyRead(
        id=dependency.id,
        organization_id=dependency.organization_id,
        upstream_risk_id=dependency.upstream_risk_id,
        downstream_risk_id=dependency.downstream_risk_id,
        relationship_type=dependency.relationship_type,
        rationale=dependency.rationale,
        created_by_user_id=dependency.created_by_user_id,
        created_at=dependency.created_at,
        updated_at=dependency.updated_at,
    )


@router.post(
    "/{risk_id}/dependencies",
    response_model=RiskDependencyRead,
    status_code=status.HTTP_201_CREATED,
)
def create_risk_dependency(
    risk_id: uuid.UUID,
    payload: RiskDependencyCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risks:write")),
) -> RiskDependencyRead:
    service = RiskDependencyService(db)
    dependency = service.create_dependency(
        org_id=organization.id,
        upstream_risk_id=risk_id,
        downstream_risk_id=payload.downstream_risk_id,
        relationship_type=payload.relationship_type,
        rationale=payload.rationale,
        created_by_user_id=current_user.id,
    )

    AuditService(db).write_audit_log(
        action="risk.dependency_created",
        entity_type="risk_dependency",
        entity_id=dependency.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "upstream_risk_id": str(dependency.upstream_risk_id),
            "downstream_risk_id": str(dependency.downstream_risk_id),
            "relationship_type": dependency.relationship_type,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(dependency)
    return _dependency_read(dependency)


@router.get("/{risk_id}/dependencies", response_model=list[RiskDependencyRead])
def list_risk_dependencies(
    risk_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risks:read")),
) -> list[RiskDependencyRead]:
    service = RiskDependencyService(db)
    dependencies = service.list_dependencies(org_id=organization.id, risk_id=risk_id)
    return [_dependency_read(d) for d in dependencies]


@router.delete("/{risk_id}/dependencies/{dependency_id}", response_model=RiskDependencyRead)
def delete_risk_dependency(
    risk_id: uuid.UUID,
    dependency_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risks:write")),
) -> RiskDependencyRead:
    service = RiskDependencyService(db)
    dependency = service.delete_dependency(org_id=organization.id, risk_id=risk_id, dependency_id=dependency_id)
    # Read the response model before commit -- the row (and thus this ORM instance) is
    # gone from the DB after commit, so attribute access afterward could raise.
    result = _dependency_read(dependency)

    AuditService(db).write_audit_log(
        action="risk.dependency_deleted",
        entity_type="risk_dependency",
        entity_id=dependency.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json={
            "upstream_risk_id": str(dependency.upstream_risk_id),
            "downstream_risk_id": str(dependency.downstream_risk_id),
            "relationship_type": dependency.relationship_type,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    return result


@router.get("/{risk_id}/dependency-graph", response_model=RiskDependencyGraph)
def get_risk_dependency_graph(
    risk_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risks:read")),
) -> RiskDependencyGraph:
    service = RiskDependencyService(db)
    graph = service.dependency_graph(org_id=organization.id, risk_id=risk_id)
    return RiskDependencyGraph(**graph)
