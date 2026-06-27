import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.services.ai_drafting_service import AIDraftingService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.draft_request import DraftRequest
from app.models.membership import Membership
from app.models.org_ai_config import OrgAIConfig
from app.models.organization import Organization
from app.models.role import Role
from app.models.user import User
from app.schemas.ai_drafting import (
    AIPolicyDraftRequest,
    AIRiskAssessmentNarrativeDraftRequest,
    ControlDescriptionDraftRequest,
    DraftApplyRequest,
    DraftRequestRead,
    EUActConformityNarrativeDraftRequest,
    EvidenceDescriptionDraftRequest,
    ModelCardContentDraftRequest,
    OrgAIConfigRead,
    PolicyContentDraftRequest,
    RCASummaryDraftRequest,
    RiskDescriptionDraftRequest,
)

router = APIRouter(prefix="/compliance/drafts", tags=["ai-drafting"])


def _require_org_admin(db: Session, membership: Membership) -> None:
    role = db.execute(select(Role).where(Role.id == membership.role_id)).scalar_one_or_none()
    if role is None or role.name not in {"owner", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Org admin role required")


def _config_read(row: OrgAIConfig) -> OrgAIConfigRead:
    return OrgAIConfigRead(
        id=row.id,
        organization_id=row.organization_id,
        ai_drafting_enabled=row.ai_drafting_enabled,
        enabled_by=row.enabled_by,
        enabled_at=row.enabled_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _draft_read(row: DraftRequest) -> DraftRequestRead:
    return DraftRequestRead(
        id=row.id,
        organization_id=row.organization_id,
        draft_type=row.draft_type,
        context_json=dict(row.context_json or {}),
        draft_output=row.draft_output,
        model_used=row.model_used,
        prompt_used=row.prompt_used,
        created_by=row.created_by,
        applied=row.applied,
        applied_at=row.applied_at,
        applied_by=row.applied_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/ai-config", response_model=OrgAIConfigRead)
def get_ai_config(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("drafts:use")),
) -> OrgAIConfigRead:
    row = AIDraftingService(db).get_or_create_ai_config(organization.id)
    db.commit()
    db.refresh(row)
    return _config_read(row)


@router.post("/ai-config/enable", response_model=OrgAIConfigRead)
def enable_ai_drafting(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("drafts:use")),
) -> OrgAIConfigRead:
    _require_org_admin(db, membership)
    row = AIDraftingService(db).enable_ai_drafting(organization.id, current_user.id)
    db.commit()
    db.refresh(row)
    return _config_read(row)


@router.post("/ai-config/disable", response_model=OrgAIConfigRead)
def disable_ai_drafting(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("drafts:use")),
) -> OrgAIConfigRead:
    _require_org_admin(db, membership)
    row = AIDraftingService(db).disable_ai_drafting(organization.id, current_user.id)
    db.commit()
    db.refresh(row)
    return _config_read(row)


@router.post("/policy-content", response_model=DraftRequestRead, status_code=status.HTTP_201_CREATED)
def draft_policy_content(
    payload: PolicyContentDraftRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("drafts:use")),
) -> DraftRequestRead:
    row = AIDraftingService(db).create_draft(
        organization.id,
        "policy_content",
        payload.model_dump(),
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _draft_read(row)


@router.post("/risk-description", response_model=DraftRequestRead, status_code=status.HTTP_201_CREATED)
def draft_risk_description(
    payload: RiskDescriptionDraftRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("drafts:use")),
) -> DraftRequestRead:
    row = AIDraftingService(db).create_draft(
        organization.id,
        "risk_description",
        payload.model_dump(),
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _draft_read(row)


@router.post("/control-description", response_model=DraftRequestRead, status_code=status.HTTP_201_CREATED)
def draft_control_description(
    payload: ControlDescriptionDraftRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("drafts:use")),
) -> DraftRequestRead:
    row = AIDraftingService(db).create_draft(
        organization.id,
        "control_description",
        payload.model_dump(),
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _draft_read(row)


@router.post("/evidence-description", response_model=DraftRequestRead, status_code=status.HTTP_201_CREATED)
def draft_evidence_description(
    payload: EvidenceDescriptionDraftRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("drafts:use")),
) -> DraftRequestRead:
    row = AIDraftingService(db).create_draft(
        organization.id,
        "evidence_description",
        payload.model_dump(),
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _draft_read(row)


@router.post("/rca-summary", response_model=DraftRequestRead, status_code=status.HTTP_201_CREATED)
def draft_rca_summary(
    payload: RCASummaryDraftRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("drafts:use")),
) -> DraftRequestRead:
    row = AIDraftingService(db).create_draft(
        organization.id,
        "rca_summary",
        payload.model_dump(),
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _draft_read(row)


@router.post("/ai-risk-assessment", response_model=DraftRequestRead, status_code=status.HTTP_201_CREATED)
def draft_ai_risk_assessment_narrative(
    payload: AIRiskAssessmentNarrativeDraftRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("drafts:use")),
) -> DraftRequestRead:
    row = AIDraftingService(db).create_draft(
        organization.id,
        "ai_risk_assessment_narrative",
        payload.model_dump(),
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _draft_read(row)


@router.post("/model-card", response_model=DraftRequestRead, status_code=status.HTTP_201_CREATED)
def draft_model_card_content(
    payload: ModelCardContentDraftRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("drafts:use")),
) -> DraftRequestRead:
    row = AIDraftingService(db).create_draft(
        organization.id,
        "model_card_content",
        payload.model_dump(),
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _draft_read(row)


@router.post("/eu-act-conformity", response_model=DraftRequestRead, status_code=status.HTTP_201_CREATED)
def draft_eu_act_conformity_narrative(
    payload: EUActConformityNarrativeDraftRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("drafts:use")),
) -> DraftRequestRead:
    row = AIDraftingService(db).create_draft(
        organization.id,
        "eu_act_conformity_narrative",
        payload.model_dump(),
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _draft_read(row)


@router.post("/ai-policy", response_model=DraftRequestRead, status_code=status.HTTP_201_CREATED)
def draft_ai_policy(
    payload: AIPolicyDraftRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("drafts:use")),
) -> DraftRequestRead:
    row = AIDraftingService(db).create_draft(
        organization.id,
        "ai_policy_draft",
        payload.model_dump(),
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _draft_read(row)


@router.get("", response_model=list[DraftRequestRead])
def list_drafts(
    draft_type: str | None = Query(default=None),
    applied: bool | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("drafts:use")),
) -> list[DraftRequestRead]:
    rows = AIDraftingService(db).list_drafts(
        organization.id,
        draft_type=draft_type,
        applied=applied,
        skip=skip,
        limit=limit,
    )
    return [_draft_read(row) for row in rows]


@router.get("/{draft_id}", response_model=DraftRequestRead)
def get_draft(
    draft_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("drafts:use")),
) -> DraftRequestRead:
    row = AIDraftingService(db).get_draft(organization.id, draft_id)
    return _draft_read(row)


@router.post("/{draft_id}/apply", response_model=DraftRequestRead)
def apply_draft(
    draft_id: uuid.UUID,
    payload: DraftApplyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("drafts:use")),
) -> DraftRequestRead:
    row = AIDraftingService(db).apply_draft(
        organization.id,
        draft_id,
        target_entity_id=payload.target_entity_id,
        target_entity_type=payload.target_entity_type,
        user_id=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _draft_read(row)
