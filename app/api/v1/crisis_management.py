from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.crisis_management import CrisisActivation, CrisisPlaybook
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.crisis_management import (
    CrisisActivationRead,
    CrisisActivationResolveRequest,
    CrisisPlaybookCreateRequest,
    CrisisPlaybookRead,
    CrisisPlaybookUpdateRequest,
)
from app.services.audit_service import AuditService
from app.services.crisis_management_service import CrisisManagementService

router = APIRouter(prefix="/crisis", tags=["crisis-management"])


def _playbook_read(playbook: CrisisPlaybook) -> CrisisPlaybookRead:
    return CrisisPlaybookRead.model_validate(playbook)


def _activation_read(activation: CrisisActivation) -> CrisisActivationRead:
    return CrisisActivationRead.model_validate(activation)


def _request_meta(request: Request) -> dict:
    return {
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }


@router.post("/playbooks", response_model=CrisisPlaybookRead, status_code=201)
def create_playbook(
    payload: CrisisPlaybookCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("crisis_management:manage")),
) -> CrisisPlaybookRead:
    service = CrisisManagementService(db)
    playbook = service.create_playbook(
        organization.id,
        data=payload.model_dump(),
        created_by_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="crisis_playbook.created",
        entity_type="crisis_playbook",
        organization_id=organization.id,
        actor_user_id=current_user.id,
        entity_id=playbook.id,
        after_json=payload.model_dump(mode="json"),
        **_request_meta(request),
    )
    db.commit()
    db.refresh(playbook)
    return _playbook_read(playbook)


@router.get("/playbooks", response_model=list[CrisisPlaybookRead])
def list_playbooks(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("crisis_management:read")),
) -> list[CrisisPlaybookRead]:
    service = CrisisManagementService(db)
    return [_playbook_read(playbook) for playbook in service.list_playbooks(organization.id)]


@router.get("/playbooks/{playbook_id}", response_model=CrisisPlaybookRead)
def get_playbook(
    playbook_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("crisis_management:read")),
) -> CrisisPlaybookRead:
    service = CrisisManagementService(db)
    playbook = service.get_playbook(organization.id, playbook_id)
    return _playbook_read(playbook)


@router.patch("/playbooks/{playbook_id}", response_model=CrisisPlaybookRead)
def update_playbook(
    playbook_id: uuid.UUID,
    payload: CrisisPlaybookUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("crisis_management:manage")),
) -> CrisisPlaybookRead:
    service = CrisisManagementService(db)
    before = service.get_playbook(organization.id, playbook_id)
    before_snapshot = _playbook_read(before).model_dump(mode="json")
    data = payload.model_dump(exclude_unset=True)
    playbook = service.update_playbook(organization.id, playbook_id, data=data)
    AuditService(db).write_audit_log(
        action="crisis_playbook.updated",
        entity_type="crisis_playbook",
        organization_id=organization.id,
        actor_user_id=current_user.id,
        entity_id=playbook.id,
        before_json=before_snapshot,
        after_json=_playbook_read(playbook).model_dump(mode="json"),
        **_request_meta(request),
    )
    db.commit()
    db.refresh(playbook)
    return _playbook_read(playbook)


@router.post("/playbooks/{playbook_id}/activate", response_model=CrisisActivationRead, status_code=201)
def activate_playbook(
    playbook_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("crisis_management:manage")),
) -> CrisisActivationRead:
    service = CrisisManagementService(db)
    activation = service.activate_playbook(
        organization.id, playbook_id, activated_by_user_id=current_user.id
    )
    AuditService(db).write_audit_log(
        action="crisis_activation.activated",
        entity_type="crisis_activation",
        organization_id=organization.id,
        actor_user_id=current_user.id,
        entity_id=activation.id,
        after_json=_activation_read(activation).model_dump(mode="json"),
        **_request_meta(request),
    )
    db.commit()
    db.refresh(activation)
    return _activation_read(activation)


@router.post("/activations/{activation_id}/resolve", response_model=CrisisActivationRead)
def resolve_activation(
    activation_id: uuid.UUID,
    payload: CrisisActivationResolveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("crisis_management:manage")),
) -> CrisisActivationRead:
    service = CrisisManagementService(db)
    before = service.get_activation(organization.id, activation_id)
    before_snapshot = _activation_read(before).model_dump(mode="json")
    activation = service.resolve_activation(
        organization.id,
        activation_id,
        resolved_by_user_id=current_user.id,
        resolution_notes=payload.resolution_notes,
    )
    AuditService(db).write_audit_log(
        action="crisis_activation.resolved",
        entity_type="crisis_activation",
        organization_id=organization.id,
        actor_user_id=current_user.id,
        entity_id=activation.id,
        before_json=before_snapshot,
        after_json=_activation_read(activation).model_dump(mode="json"),
        **_request_meta(request),
    )
    db.commit()
    db.refresh(activation)
    return _activation_read(activation)


@router.get("/active", response_model=list[CrisisActivationRead])
def list_active_activations(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("crisis_management:read")),
) -> list[CrisisActivationRead]:
    service = CrisisManagementService(db)
    return [_activation_read(activation) for activation in service.list_active_activations(organization.id)]
