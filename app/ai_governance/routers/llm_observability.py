import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.ai_governance.schemas.llm_observability import (
    CostReadingRequest,
    HallucinationCheckRequest,
    LLMObservabilityEventRead,
    LLMObservabilitySummaryRead,
    RAGEvaluationRequest,
    TracePollRequest,
)
from app.ai_governance.services.llm_observability_service import LLMObservabilityService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/ai-governance/llm-observability", tags=["ai-governance-llm-observability"])


@router.post(
    "/systems/{system_id}/trace-polls",
    response_model=list[LLMObservabilityEventRead],
    status_code=status.HTTP_201_CREATED,
)
def poll_trace_metrics(
    system_id: uuid.UUID,
    payload: TracePollRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("llm_observability:write")),
) -> list[LLMObservabilityEventRead]:
    rows = LLMObservabilityService(db).record_trace_poll(
        organization.id,
        system_id,
        public_key=payload.public_key,
        secret_key=payload.secret_key,
        base_url=payload.base_url,
        limit=payload.limit,
        actor_id=current_user.id,
    )
    db.commit()
    for row in rows:
        db.refresh(row)
    return [LLMObservabilityEventRead.model_validate(row) for row in rows]


@router.post(
    "/systems/{system_id}/hallucination-checks",
    response_model=LLMObservabilityEventRead,
    status_code=status.HTTP_201_CREATED,
)
def check_hallucination(
    system_id: uuid.UUID,
    payload: HallucinationCheckRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("llm_observability:write")),
) -> LLMObservabilityEventRead:
    row = LLMObservabilityService(db).record_hallucination_check(
        organization.id,
        system_id,
        prompt=payload.prompt,
        actual_output=payload.actual_output,
        context=payload.context,
        threshold=payload.threshold,
        actor_id=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return LLMObservabilityEventRead.model_validate(row)


@router.post(
    "/systems/{system_id}/cost-readings",
    response_model=LLMObservabilityEventRead,
    status_code=status.HTTP_201_CREATED,
)
def record_cost_reading(
    system_id: uuid.UUID,
    payload: CostReadingRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("llm_observability:write")),
) -> LLMObservabilityEventRead:
    row = LLMObservabilityService(db).record_cost_reading(
        organization.id,
        system_id,
        model=payload.model,
        input_tokens=payload.input_tokens,
        output_tokens=payload.output_tokens,
        input_price_per_million=payload.input_price_per_million,
        output_price_per_million=payload.output_price_per_million,
        actor_id=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return LLMObservabilityEventRead.model_validate(row)


@router.post(
    "/systems/{system_id}/rag-evaluations",
    response_model=list[LLMObservabilityEventRead],
    status_code=status.HTTP_201_CREATED,
)
def evaluate_rag_quality(
    system_id: uuid.UUID,
    payload: RAGEvaluationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("llm_observability:write")),
) -> list[LLMObservabilityEventRead]:
    rows = LLMObservabilityService(db).record_rag_evaluation(
        organization.id,
        system_id,
        query=payload.query,
        retrieved_contexts=payload.retrieved_contexts,
        actual_output=payload.actual_output,
        actor_id=current_user.id,
    )
    db.commit()
    for row in rows:
        db.refresh(row)
    return [LLMObservabilityEventRead.model_validate(row) for row in rows]


@router.get(
    "/systems/{system_id}/summary",
    response_model=LLMObservabilitySummaryRead,
)
def get_summary(
    system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("llm_observability:read")),
) -> LLMObservabilitySummaryRead:
    summary = LLMObservabilityService(db).get_summary(organization.id, system_id)
    return LLMObservabilitySummaryRead.model_validate(summary)
