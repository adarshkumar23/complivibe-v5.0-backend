import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_governance.services.draft_context_service import (
    build_model_card_context,
    build_risk_assessment_context,
)
from app.compliance.prompts.drafting_prompts import SYSTEM_PROMPT_MAP
from app.core.config import get_settings
from app.models.draft_request import DraftRequest
from app.models.org_ai_config import OrgAIConfig
from app.services.audit_service import AuditService


class AIDraftingService:
    ALLOWED_DRAFT_TYPES = {
        "policy_content",
        "risk_description",
        "control_description",
        "evidence_description",
        "rca_summary",
        "ai_risk_assessment_narrative",
        "model_card_content",
        "eu_act_conformity_narrative",
        "ai_policy_draft",
    }

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def get_or_create_ai_config(self, org_id: uuid.UUID) -> OrgAIConfig:
        row = self.db.execute(
            select(OrgAIConfig).where(OrgAIConfig.organization_id == org_id)
        ).scalar_one_or_none()
        if row is None:
            row = OrgAIConfig(
                organization_id=org_id,
                ai_drafting_enabled=False,
                enabled_by=None,
                enabled_at=None,
            )
            self.db.add(row)
            self.db.flush()
        return row

    def enable_ai_drafting(self, org_id: uuid.UUID, user_id: uuid.UUID) -> OrgAIConfig:
        row = self.get_or_create_ai_config(org_id)
        now = self.utcnow()
        row.ai_drafting_enabled = True
        row.enabled_by = user_id
        row.enabled_at = now
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="ai_config.enabled",
            entity_type="org_ai_config",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"ai_drafting_enabled": True, "enabled_at": now.isoformat()},
            metadata_json={"source": "api"},
        )
        return row

    def disable_ai_drafting(self, org_id: uuid.UUID, user_id: uuid.UUID) -> OrgAIConfig:
        row = self.get_or_create_ai_config(org_id)
        row.ai_drafting_enabled = False
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="ai_config.disabled",
            entity_type="org_ai_config",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"ai_drafting_enabled": False},
            metadata_json={"source": "api"},
        )
        return row

    def _check_enabled(self, org_id: uuid.UUID) -> None:
        row = self.db.execute(
            select(OrgAIConfig).where(OrgAIConfig.organization_id == org_id)
        ).scalar_one_or_none()
        if row is None or not row.ai_drafting_enabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="AI drafting is not enabled for this organization. Enable via /ai-config.",
            )

    @staticmethod
    def _require_context_key(context: dict, key: str) -> str:
        value = context.get(key)
        if value is None or str(value).strip() == "":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"context_json.{key} is required",
            )
        return str(value)

    def _build_user_prompt(self, draft_type: str, context: dict) -> str:
        if draft_type == "policy_content":
            policy_type = self._require_context_key(context, "policy_type")
            return (
                f"Draft a {policy_type} policy.\n"
                f"Scope: {context.get('scope_description', 'Not specified')}.\n"
                f"Relevant frameworks: {context.get('framework_context', 'General security')}."
            )
        if draft_type == "risk_description":
            risk_title = self._require_context_key(context, "risk_title")
            linked_controls = context.get("linked_control_titles", [])
            if not isinstance(linked_controls, list):
                linked_controls = []
            linked_text = ", ".join(str(item) for item in linked_controls)
            return (
                "Draft a risk description for:\n"
                f"Risk title: {risk_title}\n"
                f"Risk category: {context.get('risk_category', 'General')}\n"
                f"Related controls: {linked_text}"
            )
        if draft_type == "control_description":
            control_name = self._require_context_key(context, "control_name")
            return (
                "Draft a description for a control named:\n"
                f"'{control_name}'\n"
                f"Control type: {context.get('control_type', 'Not specified')}\n"
                f"Framework reference: {context.get('framework_ref', 'Not specified')}"
            )
        if draft_type == "evidence_description":
            evidence_title = self._require_context_key(context, "evidence_title")
            return (
                "Draft a description for compliance evidence:\n"
                f"Evidence title: {evidence_title}\n"
                f"Related control: {context.get('control_name', 'Not specified')}\n"
                f"Evidence type: {context.get('evidence_type', 'Not specified')}"
            )
        if draft_type == "rca_summary":
            issue_title = self._require_context_key(context, "issue_title")
            return (
                "Draft an RCA summary for:\n"
                f"Incident title: {issue_title}\n"
                f"Incident type: {context.get('issue_type', 'Not specified')}\n"
                f"Timeline: {context.get('timeline_description', 'Not provided')}"
            )
        if draft_type == "ai_risk_assessment_narrative":
            ai_system_id = uuid.UUID(self._require_context_key(context, "ai_system_id"))
            draft_context = build_risk_assessment_context(ai_system_id, self.db)
            return (
                f"Draft an AI risk assessment narrative for '{draft_context['system_name']}'. "
                f"Risk tier: {draft_context['risk_tier']}. "
                f"Bias rating: {draft_context['bias_rating']}. "
                f"Purpose: {draft_context['system_purpose']}."
            )
        if draft_type == "model_card_content":
            ai_system_id = uuid.UUID(self._require_context_key(context, "ai_system_id"))
            draft_context = build_model_card_context(ai_system_id, self.db)
            return (
                f"Draft a model card for AI system '{draft_context['system_name']}'. "
                f"Purpose: {draft_context['purpose']}. "
                f"Risk tier: {draft_context['risk_tier']}. "
                f"Deployment: {draft_context['deployment_context']}."
            )
        if draft_type == "eu_act_conformity_narrative":
            system_name = self._require_context_key(context, "system_name")
            return (
                "Draft EU AI Act conformity narrative for:\n"
                f"System name: {system_name}.\n"
                f"Article category: {context.get('article_category', 'high_risk_annex3')}.\n"
                f"Conformity route: {context.get('conformity_route', 'self_assessment')}."
            )
        if draft_type == "ai_policy_draft":
            return (
                "Draft an AI governance policy for an organization in "
                f"{context.get('industry', 'technology')}.\n"
                f"Scope: {context.get('policy_scope', 'all AI systems')}.\n"
                "Key risks to address: "
                f"{context.get('key_risks', 'bias, privacy, explainability')}."
            )
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown draft_type")

    def _call_azure_openai(self, system_prompt: str, user_prompt: str) -> str:
        settings = get_settings()
        endpoint = settings.AZURE_OPENAI_ENDPOINT
        api_key = settings.AZURE_OPENAI_API_KEY
        api_version = settings.AZURE_OPENAI_API_VERSION
        deployment = settings.AZURE_OPENAI_DEPLOYMENT
        if not endpoint or not api_key or not api_version or not deployment:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI service temporarily unavailable. Please try again.",
            )

        try:
            from openai import AzureOpenAI

            client = AzureOpenAI(
                azure_endpoint=endpoint,
                api_key=api_key,
                api_version=api_version,
            )
            response = client.chat.completions.create(
                model=deployment,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=800,
                temperature=0.3,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI service temporarily unavailable. Please try again.",
            ) from exc

        content = None
        if getattr(response, "choices", None):
            choice = response.choices[0]
            if choice is not None and getattr(choice, "message", None) is not None:
                content = choice.message.content
        if content is None or str(content).strip() == "":
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI service temporarily unavailable. Please try again.",
            )
        return str(content)

    def create_draft(
        self,
        org_id: uuid.UUID,
        draft_type: str,
        context_json: dict,
        created_by: uuid.UUID,
    ) -> DraftRequest:
        self._check_enabled(org_id)
        if draft_type not in self.ALLOWED_DRAFT_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown draft_type")

        user_prompt = self._build_user_prompt(draft_type, context_json)
        system_prompt = SYSTEM_PROMPT_MAP[draft_type]
        try:
            draft_text = self._call_azure_openai(system_prompt=system_prompt, user_prompt=user_prompt)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI service temporarily unavailable. Please try again.",
            ) from exc

        deployment = get_settings().AZURE_OPENAI_DEPLOYMENT or "azure-gpt-4o"
        row = DraftRequest(
            organization_id=org_id,
            draft_type=draft_type,
            context_json=dict(jsonable_encoder(context_json)),
            draft_output=draft_text,
            model_used=deployment,
            prompt_used=user_prompt,
            created_by=created_by,
            applied=False,
            applied_at=None,
            applied_by=None,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="draft.created",
            entity_type="draft_request",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={"draft_type": draft_type, "model_used": row.model_used, "applied": row.applied},
            metadata_json={"source": "api", "drafted_by_ai": True},
        )
        return row

    def apply_draft(
        self,
        org_id: uuid.UUID,
        draft_id: uuid.UUID,
        target_entity_id: uuid.UUID,
        target_entity_type: str,
        user_id: uuid.UUID,
    ) -> DraftRequest:
        row = self.get_draft(org_id, draft_id)
        if row.applied:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Draft already applied")

        now = self.utcnow()
        row.applied = True
        row.applied_at = now
        row.applied_by = user_id
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="draft.applied",
            entity_type="draft_request",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={
                "draft_type": row.draft_type,
                "target_entity_type": target_entity_type,
                "target_entity_id": str(target_entity_id),
                "drafted_by_ai": True,
                "applied": row.applied,
            },
            metadata_json={"source": "api"},
        )
        return row

    def get_draft(self, org_id: uuid.UUID, draft_id: uuid.UUID) -> DraftRequest:
        row = self.db.execute(
            select(DraftRequest).where(
                DraftRequest.organization_id == org_id,
                DraftRequest.id == draft_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft request not found")
        return row

    def list_drafts(
        self,
        org_id: uuid.UUID,
        draft_type: str | None = None,
        applied: bool | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[DraftRequest]:
        stmt = select(DraftRequest).where(DraftRequest.organization_id == org_id)
        if draft_type is not None:
            stmt = stmt.where(DraftRequest.draft_type == draft_type)
        if applied is not None:
            stmt = stmt.where(DraftRequest.applied == applied)
        stmt = stmt.order_by(DraftRequest.created_at.desc()).offset(skip).limit(limit)
        return self.db.execute(stmt).scalars().all()
