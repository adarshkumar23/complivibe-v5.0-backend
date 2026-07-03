from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai_governance.services.ai_provider_service import AIProviderService
from app.models.ai_content_draft import AIContentDraft
from app.models.business_unit import BusinessUnit
from app.models.organization_ai_configuration import OrganizationAIConfiguration
from app.services.compliance_policy_service import CompliancePolicyService


class PolicyDraftingService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.ai_provider = AIProviderService(db)

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _require_bu_in_org(self, org_id: uuid.UUID, business_unit_id: uuid.UUID | None) -> None:
        if business_unit_id is None:
            return
        bu = self.db.execute(
            select(BusinessUnit).where(
                BusinessUnit.id == business_unit_id,
                BusinessUnit.organization_id == org_id,
                BusinessUnit.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if bu is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business unit not found")

    def create_policy_draft(
        self,
        *,
        org_id: uuid.UUID,
        prompt_input: str,
        business_unit_id: uuid.UUID | None,
        created_by: uuid.UUID,
    ) -> AIContentDraft:
        self._require_bu_in_org(org_id, business_unit_id)
        draft_text, provider_used, used_byo_credentials = self.ai_provider.draft_policy_content(
            org_id=org_id,
            prompt_input=prompt_input,
            business_unit_id=business_unit_id,
        )
        now = self.utcnow()
        row = AIContentDraft(
            organization_id=org_id,
            business_unit_id=business_unit_id,
            content_type="policy",
            prompt_input=prompt_input,
            draft_output=draft_text,
            provider_used=provider_used,
            used_byo_credentials=used_byo_credentials,
            status="draft",
            linked_policy_id=None,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def get_draft(self, org_id: uuid.UUID, draft_id: uuid.UUID) -> AIContentDraft:
        row = self.db.execute(
            select(AIContentDraft).where(
                AIContentDraft.id == draft_id,
                AIContentDraft.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI content draft not found")
        return row

    def list_drafts(
        self,
        *,
        org_id: uuid.UUID,
        page: int,
        page_size: int,
        status_filter: str | None,
        business_unit_id: uuid.UUID | None,
    ) -> tuple[list[AIContentDraft], int]:
        stmt = select(AIContentDraft).where(AIContentDraft.organization_id == org_id)
        if status_filter is not None:
            stmt = stmt.where(AIContentDraft.status == status_filter)
        if business_unit_id is not None:
            stmt = stmt.where(AIContentDraft.business_unit_id == business_unit_id)

        total = int(self.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
        rows = self.db.execute(
            stmt.order_by(AIContentDraft.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars().all()
        return rows, total

    def accept_draft(
        self,
        *,
        org_id: uuid.UUID,
        draft_id: uuid.UUID,
        title: str,
        owner_user_id: uuid.UUID,
        description: str | None,
        review_due_date,
        effective_date,
        policy_type: str,
        accepted_by: uuid.UUID,
    ) -> tuple[AIContentDraft, uuid.UUID]:
        row = self.get_draft(org_id, draft_id)
        if row.status != "draft":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only draft status can be accepted")

        policy = CompliancePolicyService(self.db).create_policy(
            organization_id=org_id,
            title=title,
            description=description or row.draft_output,
            policy_type=policy_type,
            owner_user_id=owner_user_id,
            policy_status="draft",
            content_url=None,
            tags_json=None,
            notes="Created from AI policy draft",
            effective_date=effective_date.date() if effective_date else None,
            review_due_date=review_due_date.date() if review_due_date else None,
            business_unit_id=row.business_unit_id,
            ai_drafted=True,
            source_ai_draft_id=row.id,
        )
        now = self.utcnow()
        row.status = "accepted"
        row.linked_policy_id = policy.id
        row.updated_at = now
        self.db.flush()
        return row, policy.id

    def discard_draft(self, *, org_id: uuid.UUID, draft_id: uuid.UUID) -> AIContentDraft:
        row = self.get_draft(org_id, draft_id)
        if row.status == "accepted":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Accepted draft cannot be discarded")
        row.status = "discarded"
        row.updated_at = self.utcnow()
        self.db.flush()
        return row

    def get_or_create_org_ai_config(self, org_id: uuid.UUID) -> OrganizationAIConfiguration:
        row = self.db.execute(
            select(OrganizationAIConfiguration).where(OrganizationAIConfiguration.organization_id == org_id)
        ).scalar_one_or_none()
        if row is None:
            now = self.utcnow()
            row = OrganizationAIConfiguration(
                organization_id=org_id,
                use_byo_credentials=False,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            self.db.add(row)
            self.db.flush()
        return row

    def update_org_ai_config(
        self,
        *,
        org_id: uuid.UUID,
        use_byo_credentials: bool,
        groq_api_key: str | None,
        azure_api_key: str | None,
        azure_endpoint: str | None,
        azure_deployment_name: str | None,
        is_active: bool,
    ) -> OrganizationAIConfiguration:
        row = self.get_or_create_org_ai_config(org_id)
        row.use_byo_credentials = use_byo_credentials
        row.is_active = is_active

        if groq_api_key is not None:
            row.groq_api_key_encrypted = self.ai_provider.encrypt_credential(groq_api_key) if groq_api_key else None
        if azure_api_key is not None:
            row.azure_api_key_encrypted = self.ai_provider.encrypt_credential(azure_api_key) if azure_api_key else None
        if azure_endpoint is not None:
            row.azure_endpoint = azure_endpoint
        if azure_deployment_name is not None:
            row.azure_deployment_name = azure_deployment_name

        row.updated_at = self.utcnow()
        self.db.flush()
        return row
