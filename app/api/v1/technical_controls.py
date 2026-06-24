import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.services.technical_control_service import (
    TechnicalControlAgentService,
    TechnicalControlResultService,
    TechnicalControlRuleService,
    get_agent_from_token,
)
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.control import Control
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.technical_control_agent import TechnicalControlAgent
from app.models.technical_control_result import TechnicalControlResult
from app.models.technical_control_rule import TechnicalControlRule
from app.models.user import User
from app.schemas.technical_control import (
    TechnicalControlAgentCreate,
    TechnicalControlAgentRegistrationResponse,
    TechnicalControlAgentResponse,
    TechnicalControlIngestResponse,
    TechnicalControlOrgSummaryResponse,
    TechnicalControlResultFilters,
    TechnicalControlResultIngestRequest,
    TechnicalControlResultResponse,
    TechnicalControlRuleCreate,
    TechnicalControlRuleResponse,
    TechnicalControlRuleSummaryResponse,
    TechnicalControlRuleUpdate,
)

router = APIRouter(prefix="/compliance", tags=["technical-controls"])
ingest_router = APIRouter(prefix="/technical-control-results", tags=["technical-controls"])


def _control_ref(db: Session, control_id: uuid.UUID) -> dict:
    control = db.execute(select(Control).where(Control.id == control_id)).scalar_one_or_none()
    return {
        "id": control_id,
        "name": control.title if control is not None else "Unknown Control",
    }


def _agent_read(row: TechnicalControlAgent) -> TechnicalControlAgentResponse:
    return TechnicalControlAgentResponse(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        description=row.description,
        is_active=row.is_active,
        last_seen_at=row.last_seen_at,
        created_at=row.created_at,
    )


def _rule_read(db: Session, row: TechnicalControlRule) -> TechnicalControlRuleResponse:
    return TechnicalControlRuleResponse(
        id=row.id,
        organization_id=row.organization_id,
        control_id=row.control_id,
        name=row.name,
        description=row.description,
        target_resource_type=row.target_resource_type,
        expected_config_key=row.expected_config_key,
        expected_config_value=row.expected_config_value,
        evaluation_operator=row.evaluation_operator,
        severity=row.severity,
        is_active=row.is_active,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
        control=_control_ref(db, row.control_id),
    )


def _result_read(rule: TechnicalControlRule, row: TechnicalControlResult) -> TechnicalControlResultResponse:
    return TechnicalControlResultResponse(
        id=row.id,
        organization_id=row.organization_id,
        rule_id=row.rule_id,
        agent_id=row.agent_id,
        resource_identifier=row.resource_identifier,
        actual_config_key=row.actual_config_key,
        actual_config_value=row.actual_config_value,
        raw_payload=row.raw_payload,
        passed=row.passed,
        failure_reason=row.failure_reason,
        control_test_run_id=row.control_test_run_id,
        evaluated_at=row.evaluated_at,
        created_at=row.created_at,
        rule={"id": rule.id, "name": rule.name, "severity": rule.severity},
    )


@router.post(
    "/technical-control-agents",
    response_model=TechnicalControlAgentRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_technical_control_agent(
    payload: TechnicalControlAgentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("technical_controls:manage")),
) -> TechnicalControlAgentRegistrationResponse:
    service = TechnicalControlAgentService(db)
    row, token = service.register_agent(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return TechnicalControlAgentRegistrationResponse(**_agent_read(row).model_dump(), token=token)


@router.get("/technical-control-agents", response_model=list[TechnicalControlAgentResponse])
def list_technical_control_agents(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("technical_controls:manage")),
) -> list[TechnicalControlAgentResponse]:
    rows = TechnicalControlAgentService(db).list_agents(organization.id)
    return [_agent_read(row) for row in rows]


@router.get("/technical-control-agents/{agent_id}", response_model=TechnicalControlAgentResponse)
def get_technical_control_agent(
    agent_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("technical_controls:manage")),
) -> TechnicalControlAgentResponse:
    row = TechnicalControlAgentService(db).get_agent(organization.id, agent_id)
    return _agent_read(row)


@router.delete("/technical-control-agents/{agent_id}", response_model=TechnicalControlAgentResponse)
def deregister_technical_control_agent(
    agent_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("technical_controls:manage")),
) -> TechnicalControlAgentResponse:
    row = TechnicalControlAgentService(db).deregister_agent(organization.id, agent_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _agent_read(row)


@router.post("/technical-control-rules", response_model=TechnicalControlRuleResponse, status_code=status.HTTP_201_CREATED)
def create_technical_control_rule(
    payload: TechnicalControlRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("technical_controls:manage")),
) -> TechnicalControlRuleResponse:
    service = TechnicalControlRuleService(db)
    row = service.create_rule(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _rule_read(db, row)


@router.get("/technical-control-rules", response_model=list[TechnicalControlRuleResponse])
def list_technical_control_rules(
    control_id: uuid.UUID | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("technical_controls:manage")),
) -> list[TechnicalControlRuleResponse]:
    rows = TechnicalControlRuleService(db).list_rules(
        organization.id,
        control_id=control_id,
        is_active=is_active,
        resource_type=resource_type,
    )
    return [_rule_read(db, row) for row in rows]


@router.get("/technical-control-rules/{rule_id}", response_model=TechnicalControlRuleResponse)
def get_technical_control_rule(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("technical_controls:manage")),
) -> TechnicalControlRuleResponse:
    row = TechnicalControlRuleService(db).get_rule(organization.id, rule_id)
    return _rule_read(db, row)


@router.patch("/technical-control-rules/{rule_id}", response_model=TechnicalControlRuleResponse)
def update_technical_control_rule(
    rule_id: uuid.UUID,
    payload: TechnicalControlRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("technical_controls:manage")),
) -> TechnicalControlRuleResponse:
    service = TechnicalControlRuleService(db)
    row = service.update_rule(organization.id, rule_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _rule_read(db, row)


@router.delete("/technical-control-rules/{rule_id}", response_model=TechnicalControlRuleResponse)
def deactivate_technical_control_rule(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("technical_controls:manage")),
) -> TechnicalControlRuleResponse:
    service = TechnicalControlRuleService(db)
    row = service.deactivate_rule(organization.id, rule_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _rule_read(db, row)


@router.get("/technical-control-rules/{rule_id}/results", response_model=list[TechnicalControlResultResponse])
def list_technical_control_rule_results(
    rule_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("technical_controls:view")),
) -> list[TechnicalControlResultResponse]:
    service = TechnicalControlRuleService(db)
    rule = service.get_rule(organization.id, rule_id)
    rows = service.get_rule_results(organization.id, rule_id, limit=limit)
    return [_result_read(rule, row) for row in rows]


@router.get("/technical-control-rules/{rule_id}/summary", response_model=TechnicalControlRuleSummaryResponse)
def technical_control_rule_summary(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("technical_controls:view")),
) -> TechnicalControlRuleSummaryResponse:
    payload = TechnicalControlRuleService(db).get_rule_summary(organization.id, rule_id)
    payload.pop("severity", None)
    return TechnicalControlRuleSummaryResponse(**payload)


@router.get("/technical-control-results/summary", response_model=TechnicalControlOrgSummaryResponse)
def technical_control_org_summary(
    control_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("technical_controls:view")),
) -> TechnicalControlOrgSummaryResponse:
    payload = TechnicalControlResultService(db).get_summary(organization.id, control_id=control_id)
    return TechnicalControlOrgSummaryResponse(**payload)


@router.get("/technical-control-results", response_model=list[TechnicalControlResultResponse])
def list_technical_control_results(
    rule_id: uuid.UUID | None = Query(default=None),
    agent_id: uuid.UUID | None = Query(default=None),
    passed: bool | None = Query(default=None),
    from_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("technical_controls:view")),
) -> list[TechnicalControlResultResponse]:
    rows = TechnicalControlResultService(db).list_results(
        organization.id,
        TechnicalControlResultFilters(
            rule_id=rule_id,
            agent_id=agent_id,
            passed=passed,
            from_date=from_date,
        ),
    )
    return [_result_read(rule, result) for result, rule in rows]


@router.get("/technical-control-results/{result_id}", response_model=TechnicalControlResultResponse)
def get_technical_control_result(
    result_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("technical_controls:view")),
) -> TechnicalControlResultResponse:
    result, rule = TechnicalControlResultService(db).get_result(organization.id, result_id)
    return _result_read(rule, result)


@ingest_router.post("/ingest", response_model=TechnicalControlIngestResponse)
def ingest_technical_control_result(
    payload: TechnicalControlResultIngestRequest,
    request: Request,
    agent: TechnicalControlAgent = Depends(get_agent_from_token),
    db: Session = Depends(get_db),
) -> TechnicalControlIngestResponse:
    _ = request
    row = TechnicalControlResultService(db).ingest_result(agent, payload.rule_id, payload)
    db.commit()
    db.refresh(row)
    return TechnicalControlIngestResponse(
        result_id=row.id,
        rule_id=row.rule_id,
        passed=row.passed,
        failure_reason=row.failure_reason,
        evaluated_at=row.evaluated_at,
        control_test_run_id=row.control_test_run_id,
    )
