import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.ai_governance.schemas.ai_systems import (
    AISystemCreate,
    AISystemRead,
    AISystemStatusUpdate,
    AISystemSummaryRead,
    AISystemUpdate,
    AIUseCaseCreate,
    AIUseCaseRead,
    AIUseCaseUpdate,
)
from app.ai_governance.schemas.ai_classification import (
    AIRiskClassificationRead,
    EUAIActClassificationRead,
    EUAIActClassifyRequest,
    EUAIActObligationRead,
    EUActAnnexMappingRead,
    GuidedClassificationStartRead,
    GuidedClassificationSubmitRequest,
    ManualClassificationRequest,
    MandatoryControlsRead,
)
from app.ai_governance.schemas.bias import (
    BiasAssessmentCreate,
    BiasAssessmentResponse,
    OversightUpdateRequest,
)
from app.ai_governance.schemas.iso42001_nist_rmf import (
    NISTRMFFunctionResponseRead,
    NISTRMFImplementationDetailRead,
    NISTRMFImplementationRead,
    NISTRMFMaturityRead,
    NISTRMFSubcategoryUpdateRequest,
)
from app.ai_governance.schemas.third_party_model_card_aibom import (
    AIBOMComponentCreate,
    AIBOMComponentRead,
    AIBOMDiffRead,
    AIBOMRecordRead,
    AIBOMWithComponentsRead,
    AIBOMCreateRequest,
    ModelCardCreate,
    ModelCardRead,
    ModelCardUpdate,
)
from app.ai_governance.schemas.guardrails_envelopes import (
    ApprovalEnvelopeCreate,
    ApprovalEnvelopeRead,
    GuardrailCheckRequest,
    GuardrailCheckResult,
    GuardrailCreate,
    GuardrailRead,
)
from app.ai_governance.schemas.monitoring import (
    MonitoringConfigCreate,
    MonitoringConfigRead,
    MonitoringConfigUpdate,
    MonitoringDashboardItem,
    MonitoringDashboardRead,
    MonitoringReadingHistoryRead,
    MonitoringReadingHistorySummary,
    MonitoringReadingRead,
)
from app.ai_governance.schemas.signals_recommendations_diagnostics import (
    AIGovEventRead,
    AIRiskRecommendationRead,
    AIRiskSignalRead,
    AIRiskSignalReviewRequest,
)
from app.ai_governance.services.ai_risk_classification_service import AIRiskClassificationService
from app.ai_governance.services.ai_monitoring_service import AIMonitoringService
from app.ai_governance.services.ai_recommendation_service import AIRecommendationService
from app.ai_governance.services.ai_depth_service import AIDepthService
from app.ai_governance.services.ai_system_service import AISystemService
from app.ai_governance.services.ai_governance_event_service import AIGovernanceEventService
from app.ai_governance.services.ai_use_case_service import AIUseCaseService
from app.ai_governance.services.aibom_service import AIBOMService
from app.ai_governance.services.approval_envelope_service import ApprovalEnvelopeService
from app.ai_governance.services.eu_act_classification_service import EUAIActClassificationService
from app.ai_governance.services.guardrail_service import GuardrailService
from app.ai_governance.services.model_card_service import ModelCardService
from app.ai_governance.services.nist_rmf_service import NISTRMFService
from app.ai_governance.services.signal_service import SignalService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/ai-governance/systems", tags=["ai-governance-systems"])
scorecard_router = APIRouter(prefix="/ai-governance", tags=["ai-governance-systems"])


@router.post("", response_model=AISystemRead, status_code=status.HTTP_201_CREATED)
def create_system(
    payload: AISystemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRead:
    row = AISystemService(db).create_system(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return AISystemRead.model_validate(row)


@router.get("", response_model=list[AISystemRead])
def list_systems(
    system_type: str | None = Query(default=None),
    deployment_status: str | None = Query(default=None),
    risk_tier: str | None = Query(default=None),
    business_unit_id: uuid.UUID | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemRead]:
    rows = AISystemService(db).list_systems(
        organization.id,
        system_type=system_type,
        deployment_status=deployment_status,
        risk_tier=risk_tier,
        business_unit_id=business_unit_id,
        skip=skip,
        limit=limit,
    )
    return [AISystemRead.model_validate(row) for row in rows]


@router.get("/summary", response_model=AISystemSummaryRead)
def get_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemSummaryRead:
    payload = AISystemService(db).get_summary(organization.id)
    return AISystemSummaryRead(**payload)


@router.get("/eu-act/annex-sectors", response_model=list[EUActAnnexMappingRead])
def list_eu_act_annex_sectors(
    db: Session = Depends(get_db),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> list[EUActAnnexMappingRead]:
    rows = EUAIActClassificationService(db).list_annex_sectors()
    return [EUActAnnexMappingRead.model_validate(row) for row in rows]


@router.get("/{system_id}", response_model=AISystemRead)
def get_system(
    system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemRead:
    row = AISystemService(db).get_system(organization.id, system_id)
    return AISystemRead.model_validate(row)


@router.patch("/{system_id}", response_model=AISystemRead)
def update_system(
    system_id: uuid.UUID,
    payload: AISystemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRead:
    row = AISystemService(db).update_system(organization.id, system_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return AISystemRead.model_validate(row)


@router.post("/{system_id}/status", response_model=AISystemRead)
def update_system_status(
    system_id: uuid.UUID,
    payload: AISystemStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRead:
    row = AISystemService(db).update_deployment_status(organization.id, system_id, payload.new_status, current_user.id)
    db.commit()
    db.refresh(row)
    return AISystemRead.model_validate(row)


@router.delete("/{system_id}", response_model=AISystemRead)
def delete_system(
    system_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRead:
    row = AISystemService(db).soft_delete_system(organization.id, system_id, current_user.id)
    db.commit()
    db.refresh(row)
    return AISystemRead.model_validate(row)


@router.post("/{system_id}/classify/start", response_model=GuidedClassificationStartRead)
def start_guided_classification(
    system_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> GuidedClassificationStartRead:
    payload = AIRiskClassificationService(db).start_guided_classification(
        organization.id,
        system_id,
        {},
        current_user.id,
    )
    return GuidedClassificationStartRead(**payload)


@router.post("/{system_id}/classify/submit", response_model=AIRiskClassificationRead)
def submit_guided_classification(
    system_id: uuid.UUID,
    payload: GuidedClassificationSubmitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> AIRiskClassificationRead:
    service = AIRiskClassificationService(db)
    row = service.submit_guided_answers(
        organization.id,
        system_id,
        payload.answers,
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    return service.to_read(organization.id, row)


@router.post("/{system_id}/classify/manual", response_model=AIRiskClassificationRead)
def manual_classify(
    system_id: uuid.UUID,
    payload: ManualClassificationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> AIRiskClassificationRead:
    service = AIRiskClassificationService(db)
    row = service.manual_classify(
        organization.id,
        system_id,
        payload.risk_tier,
        payload.notes,
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    return service.to_read(organization.id, row)


@router.get("/{system_id}/classification", response_model=AIRiskClassificationRead)
def get_classification(
    system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> AIRiskClassificationRead:
    service = AIRiskClassificationService(db)
    row = service.get_classification(organization.id, system_id)
    return service.to_read(organization.id, row)


@router.get("/{system_id}/mandatory-controls", response_model=MandatoryControlsRead)
def get_mandatory_controls(
    system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> MandatoryControlsRead:
    rows = AIRiskClassificationService(db).get_mandatory_controls(organization.id, system_id)
    return MandatoryControlsRead(mandatory_controls=rows)


@router.post("/{system_id}/eu-act-classification", response_model=EUAIActClassificationRead)
def classify_eu_act(
    system_id: uuid.UUID,
    payload: EUAIActClassifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> EUAIActClassificationRead:
    row = EUAIActClassificationService(db).classify_system(organization.id, system_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return EUAIActClassificationRead.model_validate(row)


@router.get("/{system_id}/eu-act-classification", response_model=EUAIActClassificationRead)
def get_eu_act_classification(
    system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> EUAIActClassificationRead:
    row = EUAIActClassificationService(db).get_classification(organization.id, system_id)
    return EUAIActClassificationRead.model_validate(row)


@router.get("/{system_id}/eu-act-obligations", response_model=list[EUAIActObligationRead])
def get_eu_act_obligations(
    system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> list[EUAIActObligationRead]:
    rows = EUAIActClassificationService(db).get_applicable_obligations(organization.id, system_id)
    return [
        EUAIActObligationRead(
            id=row.id,
            reference_code=row.reference_code,
            title=row.title,
            description=row.description,
        )
        for row in rows
    ]


@router.post("/{system_id}/nist-rmf", response_model=NISTRMFImplementationRead)
def create_or_get_nist_rmf_implementation(
    system_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> NISTRMFImplementationRead:
    row = NISTRMFService(db).get_or_create_implementation(organization.id, system_id, current_user.id)
    db.commit()
    db.refresh(row)
    return NISTRMFImplementationRead.model_validate(row)


@router.get("/{system_id}/nist-rmf", response_model=NISTRMFImplementationDetailRead)
def get_nist_rmf_implementation(
    system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> NISTRMFImplementationDetailRead:
    service = NISTRMFService(db)
    implementation = service.get_implementation(organization.id, system_id)
    responses = service.list_responses(organization.id, implementation.id)
    return NISTRMFImplementationDetailRead(
        implementation=NISTRMFImplementationRead.model_validate(implementation),
        responses=[NISTRMFFunctionResponseRead.model_validate(row) for row in responses],
    )


@router.post("/{system_id}/nist-rmf/update-subcategory", response_model=NISTRMFImplementationDetailRead)
def update_nist_rmf_subcategory(
    system_id: uuid.UUID,
    payload: NISTRMFSubcategoryUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> NISTRMFImplementationDetailRead:
    service = NISTRMFService(db)
    implementation = service.get_implementation(organization.id, system_id)
    _ = service.update_subcategory(
        organization.id,
        implementation.id,
        payload.subcategory_ref,
        payload.response_status,
        payload.notes,
        payload.evidence_id,
        current_user.id,
        fields_set=payload.model_fields_set,
    )
    db.commit()
    db.refresh(implementation)
    responses = service.list_responses(organization.id, implementation.id)
    return NISTRMFImplementationDetailRead(
        implementation=NISTRMFImplementationRead.model_validate(implementation),
        responses=[NISTRMFFunctionResponseRead.model_validate(row) for row in responses],
    )


@router.get("/{system_id}/nist-rmf/maturity", response_model=NISTRMFMaturityRead)
def get_nist_rmf_maturity(
    system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> NISTRMFMaturityRead:
    payload = NISTRMFService(db).get_maturity(organization.id, system_id)
    return NISTRMFMaturityRead(**payload)


@router.post("/{system_id}/model-card", response_model=ModelCardRead, status_code=status.HTTP_201_CREATED)
def create_model_card(
    system_id: uuid.UUID,
    payload: ModelCardCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("model_registry:write")),
) -> ModelCardRead:
    row = ModelCardService(db).create_card(organization.id, system_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return ModelCardRead.model_validate(row)


@router.get("/{system_id}/model-card", response_model=ModelCardRead)
def get_active_model_card(
    system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("model_registry:read")),
) -> ModelCardRead:
    row = ModelCardService(db).get_active_card(organization.id, system_id)
    return ModelCardRead.model_validate(row)


@router.get("/{system_id}/model-cards", response_model=list[ModelCardRead])
def list_model_cards(
    system_id: uuid.UUID,
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("model_registry:read")),
) -> list[ModelCardRead]:
    rows = ModelCardService(db).list_cards(organization.id, system_id=system_id, status_filter=status_filter)
    return [ModelCardRead.model_validate(row) for row in rows]


@router.patch("/{system_id}/model-cards/{card_id}", response_model=ModelCardRead)
def update_model_card(
    system_id: uuid.UUID,
    card_id: uuid.UUID,
    payload: ModelCardUpdate,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("model_registry:write")),
) -> ModelCardRead:
    service = ModelCardService(db)
    card = service.get_card(organization.id, card_id)
    if card.ai_system_id != system_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model card not found")
    row = service.update_card(organization.id, card_id, payload)
    db.commit()
    db.refresh(row)
    return ModelCardRead.model_validate(row)


@router.post("/{system_id}/model-cards/{card_id}/publish", response_model=ModelCardRead)
def publish_model_card(
    system_id: uuid.UUID,
    card_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("model_registry:write")),
) -> ModelCardRead:
    service = ModelCardService(db)
    card = service.get_card(organization.id, card_id)
    if card.ai_system_id != system_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model card not found")
    row = service.publish_card(organization.id, card_id, current_user.id)
    db.commit()
    db.refresh(row)
    return ModelCardRead.model_validate(row)


@router.post("/{system_id}/aibom", response_model=AIBOMRecordRead, status_code=status.HTTP_201_CREATED)
def create_aibom(
    system_id: uuid.UUID,
    payload: AIBOMCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_bom:write")),
) -> AIBOMRecordRead:
    row = AIBOMService(db).create_aibom(
        organization.id,
        system_id,
        current_user.id,
        payload.notes,
        payload.components,
    )
    db.commit()
    db.refresh(row)
    return AIBOMRecordRead.model_validate(row)


@router.get("/{system_id}/aibom/latest", response_model=AIBOMWithComponentsRead)
def get_latest_aibom(
    system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_bom:read")),
) -> AIBOMWithComponentsRead:
    row, components = AIBOMService(db).get_latest_aibom(organization.id, system_id)
    return AIBOMWithComponentsRead(
        record=AIBOMRecordRead.model_validate(row),
        components=[AIBOMComponentRead.model_validate(component) for component in components],
    )


@router.post("/{system_id}/aibom/components", response_model=AIBOMComponentRead, status_code=status.HTTP_201_CREATED)
def add_aibom_component(
    system_id: uuid.UUID,
    payload: AIBOMComponentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_bom:write")),
) -> AIBOMComponentRead:
    service = AIBOMService(db)
    latest, _ = service.get_latest_aibom(organization.id, system_id)
    row = service.add_component(organization.id, latest.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return AIBOMComponentRead.model_validate(row)


@router.get("/{system_id}/aibom/diff", response_model=AIBOMDiffRead)
def diff_aibom_versions(
    system_id: uuid.UUID,
    v1: int = Query(..., ge=1),
    v2: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_bom:read")),
) -> AIBOMDiffRead:
    payload = AIBOMService(db).diff_versions(organization.id, system_id, v1, v2)
    return AIBOMDiffRead(**payload)


@router.post("/{system_id}/guardrails", response_model=GuardrailRead, status_code=status.HTTP_201_CREATED)
def create_system_guardrail(
    system_id: uuid.UUID,
    payload: GuardrailCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> GuardrailRead:
    data = payload.model_copy(update={"ai_system_id": system_id})
    row = GuardrailService(db).create_guardrail(organization.id, data, current_user.id)
    db.commit()
    db.refresh(row)
    return GuardrailRead.model_validate(row)


@router.get("/{system_id}/guardrails", response_model=list[GuardrailRead])
def list_system_guardrails(
    system_id: uuid.UUID,
    is_active: bool | None = Query(default=True),
    guardrail_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> list[GuardrailRead]:
    rows = GuardrailService(db).list_guardrails(
        organization.id,
        system_id=system_id,
        is_active=is_active,
        guardrail_type=guardrail_type,
    )
    return [GuardrailRead.model_validate(row) for row in rows]


@router.post("/{system_id}/guardrails/check", response_model=GuardrailCheckResult)
def check_system_guardrails(
    system_id: uuid.UUID,
    payload: GuardrailCheckRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> GuardrailCheckResult:
    result = GuardrailService(db).check_action(organization.id, system_id, payload.action_context, current_user.id)
    db.commit()
    return GuardrailCheckResult(**result)


@router.post("/{system_id}/guardrails/{guardrail_id}/deactivate", response_model=GuardrailRead)
def deactivate_system_guardrail(
    system_id: uuid.UUID,
    guardrail_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> GuardrailRead:
    service = GuardrailService(db)
    existing = service.get_guardrail(organization.id, guardrail_id)
    if existing.ai_system_id != system_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guardrail not found")
    row = service.deactivate_guardrail(organization.id, guardrail_id, current_user.id)
    if row.ai_system_id != system_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guardrail not found")
    db.commit()
    db.refresh(row)
    return GuardrailRead.model_validate(row)


@router.post("/{system_id}/approval-envelopes", response_model=ApprovalEnvelopeRead, status_code=status.HTTP_201_CREATED)
def create_system_approval_envelope(
    system_id: uuid.UUID,
    payload: ApprovalEnvelopeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> ApprovalEnvelopeRead:
    row = ApprovalEnvelopeService(db).create_envelope(
        organization.id,
        system_id,
        payload.transition_from,
        payload.transition_to,
        payload.required_approvers,
        payload.conditions,
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    return ApprovalEnvelopeRead.model_validate(row)


@router.get("/{system_id}/approval-envelopes", response_model=list[ApprovalEnvelopeRead])
def list_system_approval_envelopes(
    system_id: uuid.UUID,
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> list[ApprovalEnvelopeRead]:
    rows = ApprovalEnvelopeService(db).list_envelopes(
        organization.id,
        system_id=system_id,
        status_filter=status_filter,
    )
    db.commit()
    return [ApprovalEnvelopeRead.model_validate(row) for row in rows]


@router.post("/{system_id}/monitoring-configs", response_model=MonitoringConfigRead, status_code=status.HTTP_201_CREATED)
def create_monitoring_config(
    system_id: uuid.UUID,
    payload: MonitoringConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> MonitoringConfigRead:
    row = AIMonitoringService(db).create_config(organization.id, system_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return MonitoringConfigRead.model_validate(row).model_copy(update={"api_key_configured": row.api_key_hash is not None})


@router.get("/{system_id}/monitoring-configs", response_model=list[MonitoringConfigRead])
def list_monitoring_configs(
    system_id: uuid.UUID,
    is_active: bool | None = Query(default=None),
    metric_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> list[MonitoringConfigRead]:
    rows = AIMonitoringService(db).list_configs(
        organization.id,
        system_id=system_id,
        is_active=is_active,
        metric_type=metric_type,
    )
    return [
        MonitoringConfigRead.model_validate(row).model_copy(update={"api_key_configured": row.api_key_hash is not None})
        for row in rows
    ]


@router.patch("/{system_id}/monitoring-configs/{config_id}", response_model=MonitoringConfigRead)
def update_monitoring_config(
    system_id: uuid.UUID,
    config_id: uuid.UUID,
    payload: MonitoringConfigUpdate,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> MonitoringConfigRead:
    service = AIMonitoringService(db)
    existing = service.get_config(organization.id, config_id)
    if existing.ai_system_id != system_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitoring config not found")
    row = service.update_config(organization.id, config_id, payload)
    db.commit()
    db.refresh(row)
    return MonitoringConfigRead.model_validate(row).model_copy(update={"api_key_configured": row.api_key_hash is not None})


@router.post("/{system_id}/monitoring-configs/{config_id}/deactivate", response_model=MonitoringConfigRead)
def deactivate_monitoring_config(
    system_id: uuid.UUID,
    config_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> MonitoringConfigRead:
    service = AIMonitoringService(db)
    existing = service.get_config(organization.id, config_id)
    if existing.ai_system_id != system_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitoring config not found")
    row = service.deactivate_config(organization.id, config_id, current_user.id)
    db.commit()
    db.refresh(row)
    return MonitoringConfigRead.model_validate(row).model_copy(update={"api_key_configured": row.api_key_hash is not None})


@router.get(
    "/{system_id}/monitoring-configs/{config_id}/readings",
    response_model=MonitoringReadingHistoryRead,
)
def get_monitoring_reading_history(
    system_id: uuid.UUID,
    config_id: uuid.UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> MonitoringReadingHistoryRead:
    service = AIMonitoringService(db)
    config = service.get_config(organization.id, config_id)
    if config.ai_system_id != system_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitoring config not found")
    payload = service.list_readings(organization.id, config_id, skip=skip, limit=limit)
    return MonitoringReadingHistoryRead(
        config_id=config_id,
        metric_type=payload["config"].metric_type,
        total=payload["total"],
        readings=[MonitoringReadingRead.model_validate(row) for row in payload["readings"]],
        summary=MonitoringReadingHistorySummary(**payload["summary"]),
    )


@router.get("/{system_id}/monitoring-dashboard", response_model=MonitoringDashboardRead)
def get_monitoring_dashboard(
    system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> MonitoringDashboardRead:
    payload = AIMonitoringService(db).get_monitoring_dashboard(organization.id, system_id)
    return MonitoringDashboardRead(
        configs=[MonitoringDashboardItem(**row) for row in payload["configs"]],
        recent_breaches=[MonitoringReadingRead.model_validate(row) for row in payload["recent_breaches"]],
    )


@router.get("/{system_id}/risk-signals", response_model=list[AIRiskSignalRead])
def list_system_risk_signals(
    system_id: uuid.UUID,
    signal_type: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    severity: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> list[AIRiskSignalRead]:
    rows = SignalService(db).list_signals(
        organization.id,
        system_id=system_id,
        signal_type=signal_type,
        status_value=status_value,
        severity=severity,
        skip=skip,
        limit=limit,
    )
    return [AIRiskSignalRead.model_validate(row) for row in rows]


@router.post("/{system_id}/risk-signals/{signal_id}/review", response_model=AIRiskSignalRead)
def review_system_risk_signal(
    system_id: uuid.UUID,
    signal_id: uuid.UUID,
    payload: AIRiskSignalReviewRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("ai_governance:write")),
) -> AIRiskSignalRead:
    service = SignalService(db)
    row = service.get_signal(organization.id, signal_id)
    if row.ai_system_id != system_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI risk signal not found")
    updated = service.review_signal(
        organization.id,
        signal_id,
        action=payload.action,
        reviewer_id=membership.user_id,
        notes=payload.notes,
    )
    db.commit()
    db.refresh(updated)
    return AIRiskSignalRead.model_validate(updated)


@router.post("/{system_id}/generate-recommendations", response_model=list[AIRiskRecommendationRead])
def generate_system_recommendations(
    system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("ai_governance:write")),
) -> list[AIRiskRecommendationRead]:
    rows = AIRecommendationService(db).generate_recommendations(
        organization.id,
        system_id,
        membership.user_id,
    )
    db.commit()
    return [AIRiskRecommendationRead.model_validate(row) for row in rows]


@router.get("/{system_id}/recommendations", response_model=list[AIRiskRecommendationRead])
def list_system_recommendations(
    system_id: uuid.UUID,
    status_value: str | None = Query(default=None, alias="status"),
    priority: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> list[AIRiskRecommendationRead]:
    rows = AIRecommendationService(db).list_recommendations(
        organization.id,
        system_id=system_id,
        status_value=status_value,
        priority=priority,
    )
    return [AIRiskRecommendationRead.model_validate(row) for row in rows]


@router.get("/{system_id}/event-log", response_model=list[AIGovEventRead])
def get_system_event_log(
    system_id: uuid.UUID,
    event_type: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> list[AIGovEventRead]:
    rows = AIGovernanceEventService.get_system_events(
        db,
        organization.id,
        system_id,
        event_type=event_type,
        skip=skip,
        limit=limit,
    )
    return [AIGovEventRead.model_validate(row) for row in rows]


@router.post("/{system_id}/use-cases", response_model=AIUseCaseRead, status_code=status.HTTP_201_CREATED)
def create_use_case(
    system_id: uuid.UUID,
    payload: AIUseCaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AIUseCaseRead:
    row = AIUseCaseService(db).create_use_case(organization.id, system_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return AIUseCaseRead.model_validate(row)


@router.get("/{system_id}/use-cases", response_model=list[AIUseCaseRead])
def list_use_cases(
    system_id: uuid.UUID,
    use_case_type: str | None = Query(default=None),
    is_high_stakes: bool | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AIUseCaseRead]:
    rows = AIUseCaseService(db).list_use_cases(
        organization.id,
        system_id=system_id,
        use_case_type=use_case_type,
        is_high_stakes=is_high_stakes,
        skip=skip,
        limit=limit,
    )
    return [AIUseCaseRead.model_validate(row) for row in rows]


@router.get("/{system_id}/use-cases/{use_case_id}", response_model=AIUseCaseRead)
def get_use_case(
    system_id: uuid.UUID,
    use_case_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AIUseCaseRead:
    _ = system_id
    row = AIUseCaseService(db).get_use_case(organization.id, use_case_id)
    if row.ai_system_id != system_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI use case not found")
    return AIUseCaseRead.model_validate(row)


@router.patch("/{system_id}/use-cases/{use_case_id}", response_model=AIUseCaseRead)
def update_use_case(
    system_id: uuid.UUID,
    use_case_id: uuid.UUID,
    payload: AIUseCaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AIUseCaseRead:
    _ = system_id
    row = AIUseCaseService(db).get_use_case(organization.id, use_case_id)
    if row.ai_system_id != system_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI use case not found")
    updated = AIUseCaseService(db).update_use_case(organization.id, use_case_id, payload, current_user.id)
    db.commit()
    db.refresh(updated)
    return AIUseCaseRead.model_validate(updated)


@router.delete("/{system_id}/use-cases/{use_case_id}", response_model=AIUseCaseRead)
def delete_use_case(
    system_id: uuid.UUID,
    use_case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AIUseCaseRead:
    _ = system_id
    row = AIUseCaseService(db).get_use_case(organization.id, use_case_id)
    if row.ai_system_id != system_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI use case not found")
    updated = AIUseCaseService(db).soft_delete_use_case(organization.id, use_case_id, current_user.id)
    db.commit()
    db.refresh(updated)
    return AIUseCaseRead.model_validate(updated)


@router.post("/{system_id}/bias-assessments", response_model=BiasAssessmentResponse, status_code=status.HTTP_201_CREATED)
def submit_bias_assessment(
    system_id: uuid.UUID,
    payload: BiasAssessmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:write")),
) -> BiasAssessmentResponse:
    row = AIDepthService(db).submit_bias_assessment(
        organization.id,
        system_id,
        payload,
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    return BiasAssessmentResponse(
        id=row.id,
        system_id=row.system_id,
        assessment_method=row.assessment_method,
        protected_attribute=row.protected_attribute,
        metric_name=row.metric_name,
        metric_value=row.metric_value,
        threshold_value=row.threshold_value,
        passed=row.passed,
        remediation_notes=row.remediation_notes,
        assessed_at=row.assessed_at,
    )


@router.get("/{system_id}/bias-assessments", response_model=list[BiasAssessmentResponse])
def list_bias_assessments(
    system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:read")),
) -> list[BiasAssessmentResponse]:
    rows = AIDepthService(db).get_bias_history(organization.id, system_id)
    return [
        BiasAssessmentResponse(
            id=row.id,
            system_id=row.system_id,
            assessment_method=row.assessment_method,
            protected_attribute=row.protected_attribute,
            metric_name=row.metric_name,
            metric_value=row.metric_value,
            threshold_value=row.threshold_value,
            passed=row.passed,
            remediation_notes=row.remediation_notes,
            assessed_at=row.assessed_at,
        )
        for row in rows
    ]


@router.patch("/{system_id}/oversight", response_model=AISystemRead)
def update_oversight(
    system_id: uuid.UUID,
    payload: OversightUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:write")),
) -> AISystemRead:
    row = AIDepthService(db).update_human_oversight(
        organization.id,
        system_id,
        payload.oversight_level,
        payload.explainability_method,
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    return AISystemRead.model_validate(row)


@router.get("/{system_id}/governance-score")
def get_governance_score(
    system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:read")),
) -> dict:
    payload = AIDepthService(db).compute_data_governance_score(organization.id, system_id)
    db.commit()
    return payload


@scorecard_router.get("/scorecard")
def get_ai_governance_scorecard(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:read")),
) -> dict:
    return AIDepthService(db).get_ai_governance_scorecard(organization.id)
