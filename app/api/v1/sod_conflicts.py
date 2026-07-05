from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.sod_conflict import SodConflictFinding, SodConflictRule
from app.models.user import User
from app.schemas.sod_conflict import (
    SodConflictDetectionResponse,
    SodConflictFindingAction,
    SodConflictFindingRead,
    SodConflictRuleCreate,
    SodConflictRuleRead,
    SodConflictRuleUpdate,
)
from app.services.sod_conflict_service import SodConflictService

router = APIRouter(prefix="/sod-conflicts", tags=["sod-conflicts"])


def _rule_read(rule: SodConflictRule) -> SodConflictRuleRead:
    return SodConflictRuleRead.model_validate(rule)


def _finding_read(service: SodConflictService, finding: SodConflictFinding) -> SodConflictFindingRead:
    rule = service.get_finding_rule(finding.organization_id, finding.rule_id)
    return SodConflictFindingRead(
        id=finding.id,
        organization_id=finding.organization_id,
        user_id=finding.user_id,
        rule_id=finding.rule_id,
        permission_a=rule.permission_a if rule else None,
        permission_b=rule.permission_b if rule else None,
        severity=rule.severity if rule else None,
        detected_at=finding.detected_at,
        status=finding.status,
        acknowledged_at=finding.acknowledged_at,
        acknowledged_by=finding.acknowledged_by,
        waived_at=finding.waived_at,
        waived_by=finding.waived_by,
        note=finding.note,
        created_at=finding.created_at,
        updated_at=finding.updated_at,
    )


@router.post("/rules", response_model=SodConflictRuleRead, status_code=status.HTTP_201_CREATED)
def create_rule(
    payload: SodConflictRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("sod:manage")),
) -> SodConflictRuleRead:
    rule = SodConflictService(db).create_rule(
        organization.id,
        permission_a=payload.permission_a,
        permission_b=payload.permission_b,
        severity=payload.severity,
        description=payload.description,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(rule)
    return _rule_read(rule)


@router.get("/rules", response_model=list[SodConflictRuleRead])
def list_rules(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("sod:read")),
) -> list[SodConflictRuleRead]:
    rules = SodConflictService(db).list_rules(organization.id, include_inactive=include_inactive)
    return [_rule_read(rule) for rule in rules]


@router.get("/rules/{rule_id}", response_model=SodConflictRuleRead)
def get_rule(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("sod:read")),
) -> SodConflictRuleRead:
    return _rule_read(SodConflictService(db).get_rule(organization.id, rule_id))


@router.patch("/rules/{rule_id}", response_model=SodConflictRuleRead)
def update_rule(
    rule_id: uuid.UUID,
    payload: SodConflictRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("sod:manage")),
) -> SodConflictRuleRead:
    rule = SodConflictService(db).update_rule(
        organization.id,
        rule_id,
        permission_a=payload.permission_a,
        permission_b=payload.permission_b,
        severity=payload.severity,
        active=payload.active,
        rule_status=payload.status,
        description=payload.description,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(rule)
    return _rule_read(rule)


@router.delete("/rules/{rule_id}", response_model=SodConflictRuleRead)
def deactivate_rule(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("sod:manage")),
) -> SodConflictRuleRead:
    rule = SodConflictService(db).deactivate_rule(organization.id, rule_id, actor_user_id=current_user.id)
    db.commit()
    db.refresh(rule)
    return _rule_read(rule)


@router.get("/findings", response_model=list[SodConflictFindingRead])
def list_findings(
    finding_status: str | None = None,
    user_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("sod:read")),
) -> list[SodConflictFindingRead]:
    service = SodConflictService(db)
    findings = service.list_findings(organization.id, finding_status=finding_status, user_id=user_id)
    return [_finding_read(service, finding) for finding in findings]


@router.post("/findings/{finding_id}/acknowledge", response_model=SodConflictFindingRead)
def acknowledge_finding(
    finding_id: uuid.UUID,
    payload: SodConflictFindingAction | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("sod:manage")),
) -> SodConflictFindingRead:
    service = SodConflictService(db)
    finding = service.acknowledge_finding(
        organization.id,
        finding_id,
        actor_user_id=current_user.id,
        note=payload.note if payload else None,
    )
    db.commit()
    db.refresh(finding)
    return _finding_read(service, finding)


@router.post("/findings/{finding_id}/waive", response_model=SodConflictFindingRead)
def waive_finding(
    finding_id: uuid.UUID,
    payload: SodConflictFindingAction | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("sod:manage")),
) -> SodConflictFindingRead:
    service = SodConflictService(db)
    finding = service.waive_finding(
        organization.id,
        finding_id,
        actor_user_id=current_user.id,
        note=payload.note if payload else None,
    )
    db.commit()
    db.refresh(finding)
    return _finding_read(service, finding)


@router.post("/users/{user_id}/detect", response_model=SodConflictDetectionResponse)
def detect_user_conflicts(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("sod:manage")),
) -> SodConflictDetectionResponse:
    service = SodConflictService(db)
    findings, permission_codes = service.detect_for_user(
        organization.id,
        user_id,
        actor_user_id=current_user.id,
        source="api",
    )
    db.commit()
    return SodConflictDetectionResponse(
        user_id=user_id,
        created_finding_ids=[finding.id for finding in findings],
        permission_codes=sorted(permission_codes),
    )
