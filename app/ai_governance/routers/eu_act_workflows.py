import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.ai_governance.schemas.eu_act_workflows import (
    ConformityAssessmentCreate,
    ConformityAssessmentRead,
    ConformityAssessmentUpdate,
    ConformityChecklistItemCompleteRequest,
    FRIACreate,
    FRIARead,
    FRIAUpdate,
    PostMarketPlanCreate,
    PostMarketPlanRead,
    PostMarketPlanUpdate,
)
from app.ai_governance.services.eu_act_workflow_service import EUActWorkflowService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/ai-governance/systems", tags=["ai-governance-eu-act-workflows"])


@router.post("/{system_id}/conformity-assessment", response_model=ConformityAssessmentRead, status_code=status.HTTP_201_CREATED)
def create_conformity_assessment(
    system_id: uuid.UUID,
    payload: ConformityAssessmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> ConformityAssessmentRead:
    service = EUActWorkflowService(db)
    row = service.create_conformity_assessment(organization.id, system_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return ConformityAssessmentRead(**service.conformity_payload(row))


@router.get("/{system_id}/conformity-assessment", response_model=ConformityAssessmentRead)
def get_conformity_assessment(
    system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> ConformityAssessmentRead:
    service = EUActWorkflowService(db)
    row = service.get_conformity_assessment(organization.id, system_id)
    return ConformityAssessmentRead(**service.conformity_payload(row))


@router.patch("/{system_id}/conformity-assessment", response_model=ConformityAssessmentRead)
def update_conformity_assessment(
    system_id: uuid.UUID,
    payload: ConformityAssessmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> ConformityAssessmentRead:
    service = EUActWorkflowService(db)
    assessment = service.get_conformity_assessment(organization.id, system_id)
    row = service.update_conformity_assessment(organization.id, assessment.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return ConformityAssessmentRead(**service.conformity_payload(row))


@router.post("/{system_id}/conformity-assessment/complete-item", response_model=ConformityAssessmentRead)
def complete_conformity_checklist_item(
    system_id: uuid.UUID,
    payload: ConformityChecklistItemCompleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> ConformityAssessmentRead:
    service = EUActWorkflowService(db)
    assessment = service.get_conformity_assessment(organization.id, system_id)
    row = service.complete_checklist_item(organization.id, assessment.id, payload.item_key, current_user.id)
    db.commit()
    db.refresh(row)
    return ConformityAssessmentRead(**service.conformity_payload(row))


@router.post("/{system_id}/conformity-assessment/complete", response_model=ConformityAssessmentRead)
def complete_conformity_assessment(
    system_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> ConformityAssessmentRead:
    service = EUActWorkflowService(db)
    assessment = service.get_conformity_assessment(organization.id, system_id)
    row = service.mark_complete(organization.id, assessment.id, current_user.id)
    db.commit()
    db.refresh(row)
    return ConformityAssessmentRead(**service.conformity_payload(row))


@router.post("/{system_id}/fria", response_model=FRIARead, status_code=status.HTTP_201_CREATED)
def create_fria(
    system_id: uuid.UUID,
    payload: FRIACreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> FRIARead:
    service = EUActWorkflowService(db)
    row = service.create_fria(organization.id, system_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return FRIARead(**service.fria_payload(row))


@router.get("/{system_id}/fria", response_model=FRIARead)
def get_fria(
    system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> FRIARead:
    service = EUActWorkflowService(db)
    row = service.get_fria(organization.id, system_id)
    return FRIARead(**service.fria_payload(row))


@router.patch("/{system_id}/fria", response_model=FRIARead)
def update_fria(
    system_id: uuid.UUID,
    payload: FRIAUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> FRIARead:
    service = EUActWorkflowService(db)
    fria = service.get_fria(organization.id, system_id)
    row = service.update_fria(organization.id, fria.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return FRIARead(**service.fria_payload(row))


@router.post("/{system_id}/fria/complete", response_model=FRIARead)
def complete_fria(
    system_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> FRIARead:
    service = EUActWorkflowService(db)
    fria = service.get_fria(organization.id, system_id)
    row = service.complete_fria(organization.id, fria.id, current_user.id)
    db.commit()
    db.refresh(row)
    return FRIARead(**service.fria_payload(row))


@router.post("/{system_id}/post-market-plan", response_model=PostMarketPlanRead, status_code=status.HTTP_201_CREATED)
def create_post_market_plan(
    system_id: uuid.UUID,
    payload: PostMarketPlanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> PostMarketPlanRead:
    service = EUActWorkflowService(db)
    row = service.create_post_market_plan(organization.id, system_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return PostMarketPlanRead(**service.post_market_plan_payload(row))


@router.get("/{system_id}/post-market-plan", response_model=PostMarketPlanRead)
def get_post_market_plan(
    system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> PostMarketPlanRead:
    service = EUActWorkflowService(db)
    row = service.get_post_market_plan(organization.id, system_id)
    return PostMarketPlanRead(**service.post_market_plan_payload(row))


@router.patch("/{system_id}/post-market-plan", response_model=PostMarketPlanRead)
def update_post_market_plan(
    system_id: uuid.UUID,
    payload: PostMarketPlanUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> PostMarketPlanRead:
    service = EUActWorkflowService(db)
    plan = service.get_post_market_plan(organization.id, system_id)
    row = service.update_post_market_plan(organization.id, plan.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return PostMarketPlanRead(**service.post_market_plan_payload(row))


@router.post("/{system_id}/post-market-plan/activate", response_model=PostMarketPlanRead)
def activate_post_market_plan(
    system_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> PostMarketPlanRead:
    service = EUActWorkflowService(db)
    plan = service.get_post_market_plan(organization.id, system_id)
    row = service.activate_plan(organization.id, plan.id, current_user.id)
    db.commit()
    db.refresh(row)
    return PostMarketPlanRead(**service.post_market_plan_payload(row))
