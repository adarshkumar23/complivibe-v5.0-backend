from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai_governance.services.ai_provider_service import AIProviderService
from app.models.ai_content_draft import AIContentDraft
from app.models.ai_draft_revision import AIDraftRevision
from app.models.ai_inline_suggestion import AIInlineSuggestion
from app.models.business_unit import BusinessUnit
from app.services.audit_service import AuditService


class CopilotDraftService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.ai_provider = AIProviderService(db)
        self.audit = AuditService(db)

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _get_draft(self, org_id: uuid.UUID, draft_id: uuid.UUID) -> AIContentDraft:
        row = self.db.execute(
            select(AIContentDraft).where(
                AIContentDraft.id == draft_id,
                AIContentDraft.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI content draft not found")
        return row

    def _get_suggestion(self, org_id: uuid.UUID, suggestion_id: uuid.UUID) -> AIInlineSuggestion:
        row = self.db.execute(
            select(AIInlineSuggestion).where(
                AIInlineSuggestion.id == suggestion_id,
                AIInlineSuggestion.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI inline suggestion not found")
        return row

    def _require_bu(self, org_id: uuid.UUID, business_unit_id: uuid.UUID | None) -> None:
        if business_unit_id is None:
            return
        row = self.db.execute(
            select(BusinessUnit).where(
                BusinessUnit.id == business_unit_id,
                BusinessUnit.organization_id == org_id,
                BusinessUnit.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business unit not found")

    def _next_revision_number(self, draft_id: uuid.UUID) -> int:
        current = self.db.execute(
            select(func.max(AIDraftRevision.revision_number)).where(AIDraftRevision.draft_id == draft_id)
        ).scalar_one()
        return int(current or 0) + 1

    def refine_draft(
        self,
        *,
        org_id: uuid.UUID,
        draft_id: uuid.UUID,
        refinement_instruction: str,
        created_by: uuid.UUID,
    ) -> AIDraftRevision:
        draft = self._get_draft(org_id, draft_id)
        revisions = self.db.execute(
            select(AIDraftRevision)
            .where(
                AIDraftRevision.draft_id == draft_id,
                AIDraftRevision.organization_id == org_id,
            )
            .order_by(AIDraftRevision.revision_number.asc())
        ).scalars().all()

        revised_output, provider_used, used_byo_credentials = self.ai_provider.generate_refinement(
            org_id=org_id,
            original_prompt=draft.prompt_input,
            original_draft=draft.draft_output,
            revision_history=[
                {
                    "revision_number": row.revision_number,
                    "refinement_instruction": row.refinement_instruction,
                    "revised_output": row.revised_output,
                }
                for row in revisions
            ],
            refinement_instruction=refinement_instruction,
            content_type=draft.content_type,
        )
        revision_number = self._next_revision_number(draft_id)

        row = AIDraftRevision(
            draft_id=draft_id,
            organization_id=org_id,
            revision_number=revision_number,
            refinement_instruction=refinement_instruction,
            revised_output=revised_output,
            provider_used=provider_used,
            used_byo_credentials=used_byo_credentials,
            created_by=created_by,
            created_at=self.utcnow(),
        )
        self.db.add(row)
        self.db.flush()

        self.audit.write_audit_log(
            action="ai_content.refined",
            entity_type="ai_draft_revisions",
            organization_id=org_id,
            actor_user_id=created_by,
            entity_id=row.id,
            metadata_json={"draft_id": str(draft_id), "revision_number": revision_number, "provider_used": provider_used},
        )
        return row

    def get_revisions(self, *, org_id: uuid.UUID, draft_id: uuid.UUID) -> list[AIDraftRevision]:
        self._get_draft(org_id, draft_id)
        return self.db.execute(
            select(AIDraftRevision)
            .where(
                AIDraftRevision.draft_id == draft_id,
                AIDraftRevision.organization_id == org_id,
            )
            .order_by(AIDraftRevision.revision_number.desc())
        ).scalars().all()

    def generate_suggestions(
        self,
        *,
        org_id: uuid.UUID,
        content_type: str,
        source_text: str,
        business_unit_id: uuid.UUID | None,
        linked_entity_id: uuid.UUID | None,
        created_by: uuid.UUID,
    ) -> AIInlineSuggestion:
        self._require_bu(org_id, business_unit_id)
        suggestions, provider_used, used_byo_credentials = self.ai_provider.generate_inline_suggestions(
            org_id=org_id,
            content_type=content_type,
            source_text=source_text,
            linked_entity_context=str(linked_entity_id) if linked_entity_id else None,
        )
        row = AIInlineSuggestion(
            organization_id=org_id,
            business_unit_id=business_unit_id,
            content_type=content_type,
            source_text=source_text,
            suggestions_json=suggestions,
            linked_entity_id=linked_entity_id,
            provider_used=provider_used,
            used_byo_credentials=used_byo_credentials,
            status="pending",
            created_by=created_by,
            created_at=self.utcnow(),
            updated_at=self.utcnow(),
        )
        self.db.add(row)
        self.db.flush()
        self.audit.write_audit_log(
            action="ai_content.suggestions_generated",
            entity_type="ai_inline_suggestions",
            organization_id=org_id,
            actor_user_id=created_by,
            entity_id=row.id,
            metadata_json={"content_type": content_type, "provider_used": provider_used},
        )
        return row

    def apply_suggestion(self, *, org_id: uuid.UUID, suggestion_id: uuid.UUID, created_by: uuid.UUID) -> AIInlineSuggestion:
        row = self._get_suggestion(org_id, suggestion_id)
        row.status = "applied"
        row.updated_at = self.utcnow()
        self.db.flush()
        self.audit.write_audit_log(
            action="ai_content.suggestion_applied",
            entity_type="ai_inline_suggestions",
            organization_id=org_id,
            actor_user_id=created_by,
            entity_id=row.id,
            metadata_json={"status": row.status},
        )
        return row

    def dismiss_suggestion(
        self,
        *,
        org_id: uuid.UUID,
        suggestion_id: uuid.UUID,
        created_by: uuid.UUID,
    ) -> AIInlineSuggestion:
        row = self._get_suggestion(org_id, suggestion_id)
        row.status = "dismissed"
        row.updated_at = self.utcnow()
        self.db.flush()
        self.audit.write_audit_log(
            action="ai_content.suggestion_dismissed",
            entity_type="ai_inline_suggestions",
            organization_id=org_id,
            actor_user_id=created_by,
            entity_id=row.id,
            metadata_json={"status": row.status},
        )
        return row
