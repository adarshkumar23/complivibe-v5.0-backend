from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.compliance.schemas.copilot_draft import (
    DraftRefineRequest,
    DraftRefineResponse,
    DraftRevisionRead,
    InlineSuggestRequest,
    InlineSuggestResponse,
    SuggestionStatusResponse,
)
from app.compliance.services.ai_drafting_service import AIDraftingService
from app.compliance.services.copilot_draft_service import CopilotDraftService
from app.core.billing_deps import require_feature
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(tags=["copilot-draft"])

# See the gating story documented at the top of
# app/compliance/routers/policy_drafting.py: this router is part of the
# free-form/prompt-based drafting family, gated by BOTH the org-level AI
# drafting toggle and the "ai_policy_drafting" billing plan feature. Only the
# endpoints that trigger a *new* AI generation (refine_draft,
# generate_inline_suggestions) enforce the org toggle; reviewing revisions or
# applying/dismissing an already-generated suggestion does not.


def _revision_read(row) -> DraftRevisionRead:
    return DraftRevisionRead(
        id=row.id,
        draft_id=row.draft_id,
        organization_id=row.organization_id,
        revision_number=row.revision_number,
        refinement_instruction=row.refinement_instruction,
        revised_output=row.revised_output,
        provider_used=row.provider_used,
        used_byo_credentials=row.used_byo_credentials,
        created_by=row.created_by,
        created_at=row.created_at,
    )


@router.post(
    "/compliance/draft/{draft_id}/refine",
    response_model=DraftRefineResponse,
    description=(
        "Generates a new AI revision of an existing free-form draft. Requires BOTH the "
        "org-level AI drafting toggle and the 'ai_policy_drafting' billing plan feature "
        "(see gating story in app/compliance/routers/policy_drafting.py)."
    ),
)
def refine_draft(
    draft_id: uuid.UUID,
    payload: DraftRefineRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:write")),
    __: Organization = require_feature("ai_policy_drafting"),
) -> DraftRefineResponse:
    AIDraftingService(db).ensure_ai_drafting_enabled(organization.id)
    row = CopilotDraftService(db).refine_draft(
        org_id=organization.id,
        draft_id=draft_id,
        refinement_instruction=payload.refinement_instruction,
        created_by=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return DraftRefineResponse(
        draft_id=row.draft_id,
        revision_id=row.id,
        revision_number=row.revision_number,
        revised_output=row.revised_output,
        provider_used=row.provider_used,
        used_byo_credentials=row.used_byo_credentials,
    )


@router.get("/compliance/draft/{draft_id}/revisions", response_model=list[DraftRevisionRead])
def list_draft_revisions(
    draft_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:read")),
    __: Organization = require_feature("ai_policy_drafting"),
) -> list[DraftRevisionRead]:
    rows = CopilotDraftService(db).get_revisions(org_id=organization.id, draft_id=draft_id)
    return [_revision_read(row) for row in rows]


@router.post(
    "/compliance/suggest",
    response_model=InlineSuggestResponse,
    description=(
        "Generates new AI inline suggestions for a piece of content. Requires BOTH the "
        "org-level AI drafting toggle and the 'ai_policy_drafting' billing plan feature "
        "(see gating story in app/compliance/routers/policy_drafting.py)."
    ),
)
def generate_inline_suggestions(
    payload: InlineSuggestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:write")),
    __: Organization = require_feature("ai_policy_drafting"),
) -> InlineSuggestResponse:
    AIDraftingService(db).ensure_ai_drafting_enabled(organization.id)
    row = CopilotDraftService(db).generate_suggestions(
        org_id=organization.id,
        content_type=payload.content_type,
        source_text=payload.source_text,
        business_unit_id=payload.business_unit_id,
        linked_entity_id=payload.linked_entity_id,
        created_by=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return InlineSuggestResponse(
        id=row.id,
        organization_id=row.organization_id,
        business_unit_id=row.business_unit_id,
        content_type=row.content_type,
        suggestions_json=row.suggestions_json,
        provider_used=row.provider_used,
        used_byo_credentials=row.used_byo_credentials,
        status=row.status,
        created_at=row.created_at,
    )


@router.post("/compliance/suggest/{suggestion_id}/apply", response_model=SuggestionStatusResponse)
def apply_inline_suggestion(
    suggestion_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:write")),
    __: Organization = require_feature("ai_policy_drafting"),
) -> SuggestionStatusResponse:
    row = CopilotDraftService(db).apply_suggestion(
        org_id=organization.id,
        suggestion_id=suggestion_id,
        created_by=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return SuggestionStatusResponse(id=row.id, status=row.status)


@router.post("/compliance/suggest/{suggestion_id}/dismiss", response_model=SuggestionStatusResponse)
def dismiss_inline_suggestion(
    suggestion_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:write")),
    __: Organization = require_feature("ai_policy_drafting"),
) -> SuggestionStatusResponse:
    row = CopilotDraftService(db).dismiss_suggestion(
        org_id=organization.id,
        suggestion_id=suggestion_id,
        created_by=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return SuggestionStatusResponse(id=row.id, status=row.status)
