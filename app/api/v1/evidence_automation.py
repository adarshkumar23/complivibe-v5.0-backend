import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.evidence_automation import (
    EvidenceAutomationIngestDuplicate,
    EvidenceAutomationIngestError,
    EvidenceAutomationIngestPayload,
    EvidenceAutomationIngestResponse,
    EvidenceAutomationRuleCreate,
    EvidenceAutomationRuleRead,
    EvidenceAutomationRuleUpdate,
)
from app.services.audit_service import AuditService
from app.services.evidence_automation_service import EvidenceAutomationService

router = APIRouter(prefix="/evidence-automation", tags=["evidence-automation"])


def _rule_read(row, service: EvidenceAutomationService) -> EvidenceAutomationRuleRead:
    health = service.describe_rule_health(row)
    return EvidenceAutomationRuleRead(
        id=row.id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        organization_id=row.organization_id,
        trigger_source=row.trigger_source,
        trigger_config=row.trigger_config or {},
        target_control_id=row.target_control_id,
        evidence_type=row.evidence_type,
        transform_template=row.transform_template,
        is_active=row.is_active,
        created_by_user_id=row.created_by_user_id,
        last_triggered_at=row.last_triggered_at,
        last_matched_at=row.last_matched_at,
        trigger_count=row.trigger_count,
        consecutive_error_count=row.consecutive_error_count,
        last_error_at=row.last_error_at,
        last_error_message=row.last_error_message,
        is_stale=health["is_stale"],
        needs_attention=health["needs_attention"],
        target_control_archived=health["target_control_archived"],
        context_flags=health["context_flags"],
    )


@router.get("/rules", response_model=list[EvidenceAutomationRuleRead])
def list_rules(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("evidence_automation_rules:read")),
) -> list[EvidenceAutomationRuleRead]:
    service = EvidenceAutomationService(db)
    rows = service.list_rules(organization.id)
    return [_rule_read(row, service) for row in rows]


@router.post("/rules", response_model=EvidenceAutomationRuleRead, status_code=status.HTTP_201_CREATED)
def create_rule(
    payload: EvidenceAutomationRuleCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("evidence_automation_rules:write")),
) -> EvidenceAutomationRuleRead:
    service = EvidenceAutomationService(db)
    row = service.create_rule(
        organization_id=organization.id,
        created_by_user_id=current_user.id,
        trigger_source=payload.trigger_source,
        trigger_config=payload.trigger_config,
        target_control_id=payload.target_control_id,
        evidence_type=payload.evidence_type,
        transform_template=payload.transform_template,
        is_active=payload.is_active,
    )
    AuditService(db).write_audit_log(
        action="evidence_automation_rule.created",
        entity_type="evidence_automation_rule",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"trigger_source": row.trigger_source, "evidence_type": row.evidence_type, "is_active": row.is_active},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _rule_read(row, service)


@router.patch("/rules/{rule_id}", response_model=EvidenceAutomationRuleRead)
def update_rule(
    rule_id: uuid.UUID,
    payload: EvidenceAutomationRuleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("evidence_automation_rules:write")),
) -> EvidenceAutomationRuleRead:
    service = EvidenceAutomationService(db)
    row = service.get_rule(organization.id, rule_id)
    before = {
        "trigger_config": row.trigger_config,
        "target_control_id": str(row.target_control_id) if row.target_control_id else None,
        "evidence_type": row.evidence_type,
        "transform_template": row.transform_template,
        "is_active": row.is_active,
    }

    if payload.trigger_config is not None:
        try:
            service.validate_trigger_config(payload.trigger_config)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        row.trigger_config = payload.trigger_config
    if payload.target_control_id is not None:
        service.evidence_service.require_control_in_org(organization.id, payload.target_control_id)
        row.target_control_id = payload.target_control_id
    if payload.evidence_type is not None:
        row.evidence_type = payload.evidence_type
    if payload.transform_template is not None:
        try:
            service._parse_transform_template(payload.transform_template)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        row.transform_template = payload.transform_template
    if payload.is_active is not None:
        row.is_active = payload.is_active

    db.flush()
    AuditService(db).write_audit_log(
        action="evidence_automation_rule.updated",
        entity_type="evidence_automation_rule",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "trigger_config": row.trigger_config,
            "target_control_id": str(row.target_control_id) if row.target_control_id else None,
            "evidence_type": row.evidence_type,
            "transform_template": row.transform_template,
            "is_active": row.is_active,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _rule_read(row, service)


def _ingest_response(
    *,
    source: str,
    evidence_item_ids: list[uuid.UUID],
    matched_rule_count: int,
    skipped_rule_count: int,
    errors: list[tuple[uuid.UUID, str]],
    duplicates: list[tuple[uuid.UUID, str]],
) -> EvidenceAutomationIngestResponse:
    return EvidenceAutomationIngestResponse(
        source=source,
        matched_rule_count=matched_rule_count,
        skipped_rule_count=skipped_rule_count,
        created_count=len(evidence_item_ids),
        duplicate_count=len(duplicates),
        evidence_item_ids=evidence_item_ids,
        errors=[EvidenceAutomationIngestError(rule_id=rule_id, reason=reason) for rule_id, reason in errors],
        duplicates=[
            EvidenceAutomationIngestDuplicate(rule_id=rule_id, idempotency_key=key) for rule_id, key in duplicates
        ],
    )


def _ingest_source(
    *,
    source: str,
    payload: EvidenceAutomationIngestPayload,
    request: Request,
    db: Session,
    current_user: User,
    organization: Organization,
) -> EvidenceAutomationIngestResponse:
    service = EvidenceAutomationService(db)
    created, errors, skipped, duplicates = service.ingest(
        organization_id=organization.id,
        actor_user_id=current_user.id,
        source=source,
        payload=payload.payload,
        received_at=payload.received_at,
        request_ip=request.client.host if request.client else None,
        request_user_agent=request.headers.get("user-agent"),
    )
    AuditService(db).write_audit_log(
        action=f"evidence_automation_ingest.{source}",
        entity_type="evidence_automation_rule",
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "source": source,
            "created_count": len(created),
            "error_count": len(errors),
            "skipped_rule_count": skipped,
            "duplicate_count": len(duplicates),
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return _ingest_response(
        source=source,
        evidence_item_ids=[row.id for row in created],
        matched_rule_count=len(created) + len(errors) + len(duplicates),
        skipped_rule_count=skipped,
        errors=errors,
        duplicates=duplicates,
    )


@router.post("/inbound/webhook", response_model=EvidenceAutomationIngestResponse)
def ingest_webhook(
    payload: EvidenceAutomationIngestPayload,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("evidence_automation_ingest:webhook")),
) -> EvidenceAutomationIngestResponse:
    return _ingest_source(
        source="webhook",
        payload=payload,
        request=request,
        db=db,
        current_user=current_user,
        organization=organization,
    )


@router.post("/inbound/email-parse", response_model=EvidenceAutomationIngestResponse)
def ingest_email_parse(
    payload: EvidenceAutomationIngestPayload,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("evidence_automation_ingest:email")),
) -> EvidenceAutomationIngestResponse:
    return _ingest_source(
        source="email",
        payload=payload,
        request=request,
        db=db,
        current_user=current_user,
        organization=organization,
    )


@router.post("/inbound/form-submit", response_model=EvidenceAutomationIngestResponse)
def ingest_form_submit(
    payload: EvidenceAutomationIngestPayload,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("evidence_automation_ingest:form")),
) -> EvidenceAutomationIngestResponse:
    return _ingest_source(
        source="form",
        payload=payload,
        request=request,
        db=db,
        current_user=current_user,
        organization=organization,
    )
