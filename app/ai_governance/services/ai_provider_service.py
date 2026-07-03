from __future__ import annotations

import base64
import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from cryptography.fernet import Fernet
from fastapi import HTTPException, status
from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.organization_ai_configuration import OrganizationAIConfiguration


@dataclass
class ResolvedAICredentials:
    use_byo_credentials: bool
    groq_api_key: str | None
    azure_api_key: str | None
    azure_endpoint: str | None
    azure_deployment_name: str | None


class AIProviderService:
    GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
    CONTENT_TYPES = {"policy", "control", "risk"}
    DRAFT_SYSTEM_PROMPTS = {
        "policy": (
            "You are an enterprise compliance policy drafting assistant. "
            "Draft concise, implementation-ready policy text with sections for purpose, scope, requirements, "
            "roles, monitoring, and review cadence."
        ),
        "control": (
            "You are an enterprise compliance controls assistant. "
            "Draft control statements that are testable, specific, and include objective evidence expectations."
        ),
        "risk": (
            "You are an enterprise risk analyst. "
            "Draft risk descriptions with threat, impact, and likelihood language suitable for a risk register."
        ),
    }
    RISK_RECOMMENDATION_TYPES = {
        "gap_identified",
        "treatment_change",
        "new_risk",
        "risk_retirement",
    }

    def __init__(self, db: Session) -> None:
        self.db = db
        self.fernet = Fernet(self._resolve_fernet_key())

    @staticmethod
    def _resolve_fernet_key() -> bytes:
        settings = get_settings()
        raw = (settings.FERNET_SECRET_KEY or "").strip()
        if raw:
            return raw.encode("utf-8")

        digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)

    def encrypt_credential(self, value: str) -> str:
        return self.fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt_credential(self, value: str) -> str:
        return self.fernet.decrypt(value.encode("utf-8")).decode("utf-8")

    def get_or_create_org_config(self, org_id: uuid.UUID) -> OrganizationAIConfiguration:
        row = self.db.execute(
            select(OrganizationAIConfiguration).where(OrganizationAIConfiguration.organization_id == org_id)
        ).scalar_one_or_none()
        if row is None:
            ts = datetime.now(UTC)
            row = OrganizationAIConfiguration(
                organization_id=org_id,
                use_byo_credentials=False,
                is_active=True,
                created_at=ts,
                updated_at=ts,
            )
            self.db.add(row)
            self.db.flush()
        return row

    def resolve_credentials(self, org_id: uuid.UUID) -> ResolvedAICredentials:
        settings = get_settings()
        row = self.db.execute(
            select(OrganizationAIConfiguration).where(OrganizationAIConfiguration.organization_id == org_id)
        ).scalar_one_or_none()

        if row and row.use_byo_credentials and row.is_active:
            groq = self.decrypt_credential(row.groq_api_key_encrypted) if row.groq_api_key_encrypted else None
            azure = self.decrypt_credential(row.azure_api_key_encrypted) if row.azure_api_key_encrypted else None
            return ResolvedAICredentials(
                use_byo_credentials=True,
                groq_api_key=groq,
                azure_api_key=azure,
                azure_endpoint=row.azure_endpoint,
                azure_deployment_name=row.azure_deployment_name,
            )

        return ResolvedAICredentials(
            use_byo_credentials=False,
            groq_api_key=settings.GROQ_API_KEY or None,
            azure_api_key=settings.AZURE_OPENAI_API_KEY or None,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            azure_deployment_name=(settings.AZURE_OPENAI_DEPLOYMENT_NAME or settings.AZURE_OPENAI_DEPLOYMENT),
        )

    def draft_policy_content(
        self,
        org_id: uuid.UUID,
        prompt_input: str,
        business_unit_id: uuid.UUID | None = None,
    ) -> tuple[str, str, bool]:
        return self._generate_content(
            org_id=org_id,
            content_type="policy",
            prompt_input=prompt_input,
            business_unit_id=business_unit_id,
        )

    def _generate_content(
        self,
        *,
        org_id: uuid.UUID,
        content_type: str,
        prompt_input: str,
        business_unit_id: uuid.UUID | None = None,
    ) -> tuple[str, str, bool]:
        if content_type not in self.CONTENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported content_type '{content_type}'",
            )
        messages = [
            {"role": "system", "content": self._system_prompt(content_type)},
            {"role": "user", "content": self._user_prompt(prompt_input, business_unit_id)},
        ]
        return self._run_provider_chain(org_id=org_id, messages=messages, failure_context="AI drafting unavailable")

    def generate_refinement(
        self,
        *,
        org_id: uuid.UUID,
        original_prompt: str,
        original_draft: str,
        revision_history: list[dict],
        refinement_instruction: str,
        content_type: str = "policy",
    ) -> tuple[str, str, bool]:
        if content_type not in self.CONTENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported content_type '{content_type}'",
            )

        history_blocks: list[str] = []
        for item in revision_history:
            rev_no = item.get("revision_number")
            instr = item.get("refinement_instruction", "")
            out = item.get("revised_output", "")
            history_blocks.append(
                f"Revision {rev_no} instruction:\n{instr}\n\nRevision {rev_no} output:\n{out}"
            )

        history_text = "\n\n".join(history_blocks) if history_blocks else "No prior revisions."
        user_prompt = (
            f"Original user request:\n{original_prompt}\n\n"
            f"Original draft text:\n{original_draft}\n\n"
            f"Revision history:\n{history_text}\n\n"
            f"Current refinement instruction:\n{refinement_instruction}\n\n"
            "Return only the revised draft text, fully rewritten with the requested edits."
        )
        messages = [
            {"role": "system", "content": self._system_prompt(content_type)},
            {"role": "user", "content": user_prompt},
        ]
        return self._run_provider_chain(
            org_id=org_id,
            messages=messages,
            failure_context="AI refinement unavailable",
        )

    def generate_inline_suggestions(
        self,
        *,
        org_id: uuid.UUID,
        content_type: str,
        source_text: str,
        linked_entity_context: str | None = None,
    ) -> tuple[list[dict], str, bool]:
        if content_type not in self.CONTENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported content_type '{content_type}'",
            )
        context_line = f"Entity context: {linked_entity_context}" if linked_entity_context else "Entity context: none"
        prompt = (
            f"Analyze this {content_type} text and provide improvement suggestions.\n"
            f"{context_line}\n\n"
            "Return ONLY valid JSON array. Each item must contain keys: "
            "original_fragment, suggested_replacement, reasoning, category.\n"
            "Allowed category values: clarity, completeness, compliance_language, risk_coverage.\n\n"
            f"Source text:\n{source_text}"
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a compliance writing copilot. Output strictly JSON array with no markdown fences."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        parse_error: Exception | None = None
        for attempt in range(2):
            text, provider_used, used_byo = self._run_provider_chain(
                org_id=org_id,
                messages=messages,
                failure_context="AI suggestions unavailable",
            )
            try:
                return self._parse_suggestions_json(text), provider_used, used_byo
            except Exception as exc:  # noqa: BLE001
                parse_error = exc
                messages.append(
                    {
                        "role": "assistant",
                        "content": text,
                    }
                )
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your previous response was not valid for parsing. "
                            "Return ONLY a valid JSON array with required keys."
                        ),
                    }
                )
                if attempt == 1:
                    break

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI suggestions parsing failed after retry: {parse_error}",
        )

    def generate_risk_recommendations(
        self,
        *,
        org_id: uuid.UUID,
        context_data: dict,
        business_unit_id: uuid.UUID | None = None,
    ) -> tuple[list[dict], str, bool]:
        scope_line = "organization-wide"
        if business_unit_id is not None:
            scope_line = f"business-unit scoped ({business_unit_id})"
        if context_data.get("business_unit_name"):
            scope_line += f", name={context_data['business_unit_name']}"

        prompt = (
            "Generate 3 to 7 enterprise compliance risk recommendations.\n"
            f"Scope: {scope_line}\n"
            "Output MUST be ONLY a JSON array with no markdown, no prose, no explanation.\n"
            "Each object must contain exactly these keys:\n"
            "recommendation_type, title, rationale, suggested_category, suggested_likelihood, "
            "suggested_impact, suggested_treatment, linked_risk_title.\n"
            "Allowed recommendation_type values: gap_identified, treatment_change, new_risk, risk_retirement.\n"
            "title max 250 chars.\n"
            "likelihood/impact must be integer 1-5 or null.\n"
            "Use linked_risk_title only for treatment_change or risk_retirement.\n\n"
            f"Context JSON:\n{json.dumps(context_data, ensure_ascii=True)}"
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a compliance risk advisor. Return strictly valid JSON array only; "
                    "do not include markdown fences."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        parse_error: Exception | None = None
        for attempt in range(2):
            text, provider_used, used_byo = self._run_provider_chain(
                org_id=org_id,
                messages=messages,
                failure_context="AI risk recommendation generation unavailable",
            )
            try:
                parsed = self._parse_risk_recommendations_json(text)
                if not parsed:
                    raise ValueError("AI returned empty recommendations")
                return parsed, provider_used, used_byo
            except Exception as exc:  # noqa: BLE001
                parse_error = exc
                messages.append({"role": "assistant", "content": text})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your previous output was invalid. Return ONLY a JSON array "
                            "with 3-7 recommendation objects and required keys."
                        ),
                    }
                )
                if attempt == 1:
                    break

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI recommendations parsing failed after retry: {parse_error}",
        )

    def _run_provider_chain(
        self,
        *,
        org_id: uuid.UUID,
        messages: list[dict[str, str]],
        failure_context: str,
    ) -> tuple[str, str, bool]:
        creds = self.resolve_credentials(org_id)

        groq_exc: Exception | None = None
        if creds.groq_api_key:
            try:
                text = self._call_groq_messages(creds.groq_api_key, messages)
                return text, "groq", creds.use_byo_credentials
            except Exception as exc:  # noqa: BLE001
                groq_exc = exc

        azure_exc: Exception | None = None
        if creds.azure_api_key and creds.azure_endpoint and creds.azure_deployment_name:
            try:
                text = self._call_azure_messages(
                    api_key=creds.azure_api_key,
                    endpoint=creds.azure_endpoint,
                    deployment_name=creds.azure_deployment_name,
                    messages=messages,
                )
                return text, "azure", creds.use_byo_credentials
            except Exception as exc:  # noqa: BLE001
                azure_exc = exc

        detail = f"{failure_context}: both Groq primary and Azure fallback failed"
        if groq_exc:
            detail += f"; groq_error={groq_exc}"
        if azure_exc:
            detail += f"; azure_error={azure_exc}"

        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)

    def _system_prompt(self, content_type: str) -> str:
        return self.DRAFT_SYSTEM_PROMPTS[content_type]

    def _user_prompt(self, prompt_input: str, business_unit_id: uuid.UUID | None) -> str:
        bu_line = f"Business unit scope: {business_unit_id}." if business_unit_id else "Scope: organization-wide."
        return f"{bu_line}\nUser request:\n{prompt_input}\nReturn plain policy text."

    def _call_groq(self, api_key: str, prompt_input: str, business_unit_id: uuid.UUID | None) -> str:
        return self._call_groq_messages(
            api_key=api_key,
            messages=[
                {"role": "system", "content": self._system_prompt("policy")},
                {"role": "user", "content": self._user_prompt(prompt_input, business_unit_id)},
            ],
        )

    def _call_groq_messages(self, api_key: str, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 1200,
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                self.GROQ_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        text = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content")
        )
        if not text or not str(text).strip():
            raise RuntimeError("Groq returned empty draft text")
        return str(text)

    def _call_azure(
        self,
        *,
        api_key: str,
        endpoint: str,
        deployment_name: str,
        prompt_input: str,
        business_unit_id: uuid.UUID | None,
    ) -> str:
        return self._call_azure_messages(
            api_key=api_key,
            endpoint=endpoint,
            deployment_name=deployment_name,
            messages=[
                {"role": "system", "content": self._system_prompt("policy")},
                {"role": "user", "content": self._user_prompt(prompt_input, business_unit_id)},
            ],
        )

    def _call_azure_messages(
        self,
        *,
        api_key: str,
        endpoint: str,
        deployment_name: str,
        messages: list[dict[str, str]],
    ) -> str:
        client = OpenAI(
            api_key=api_key,
            base_url=endpoint,
            timeout=30.0,
        )
        resp = client.chat.completions.create(
            model=deployment_name,
            messages=messages,
            temperature=0.2,
            max_tokens=1200,
        )
        text = None
        if getattr(resp, "choices", None):
            msg = resp.choices[0].message if resp.choices[0] else None
            text = msg.content if msg else None
        if not text or not str(text).strip():
            raise RuntimeError("Azure returned empty draft text")
        return str(text)

    @staticmethod
    def _parse_suggestions_json(text: str) -> list[dict]:
        body = text.strip()
        fence_match = re.search(r"```(?:json)?\s*(.*?)```", body, flags=re.DOTALL | re.IGNORECASE)
        if fence_match:
            body = fence_match.group(1).strip()

        if not body.startswith("["):
            list_match = re.search(r"(\[\s*\{.*\}\s*\])", body, flags=re.DOTALL)
            if list_match:
                body = list_match.group(1)

        parsed = json.loads(body)
        if not isinstance(parsed, list) or not parsed:
            raise ValueError("Suggestions output must be a non-empty JSON list")

        required = {"original_fragment", "suggested_replacement", "reasoning", "category"}
        normalized: list[dict] = []
        for item in parsed:
            if not isinstance(item, dict):
                raise ValueError("Each suggestion must be an object")
            if not required.issubset(item.keys()):
                raise ValueError("Suggestion is missing required keys")
            normalized.append(
                {
                    "original_fragment": str(item["original_fragment"]),
                    "suggested_replacement": str(item["suggested_replacement"]),
                    "reasoning": str(item["reasoning"]),
                    "category": str(item["category"]),
                }
            )
        return normalized

    def _parse_risk_recommendations_json(self, text: str) -> list[dict]:
        body = text.strip()
        fence_match = re.search(r"```(?:json)?\s*(.*?)```", body, flags=re.DOTALL | re.IGNORECASE)
        if fence_match:
            body = fence_match.group(1).strip()

        if not body.startswith("["):
            list_match = re.search(r"(\[\s*\{.*\}\s*\])", body, flags=re.DOTALL)
            if list_match:
                body = list_match.group(1)

        parsed = json.loads(body)
        if not isinstance(parsed, list):
            raise ValueError("Recommendations output must be a JSON list")
        if not 3 <= len(parsed) <= 7:
            raise ValueError("Recommendations list size must be between 3 and 7")

        normalized: list[dict] = []
        for item in parsed:
            if not isinstance(item, dict):
                raise ValueError("Each recommendation must be an object")

            recommendation_type = str(item.get("recommendation_type", "")).strip()
            if recommendation_type not in self.RISK_RECOMMENDATION_TYPES:
                raise ValueError("Invalid recommendation_type in AI response")

            title = str(item.get("title", "")).strip()
            if not title:
                raise ValueError("Recommendation title is required")
            if len(title) > 250:
                title = title[:250]

            rationale = str(item.get("rationale", "")).strip()
            if not rationale:
                raise ValueError("Recommendation rationale is required")

            raw_likelihood = item.get("suggested_likelihood")
            raw_impact = item.get("suggested_impact")
            likelihood = None if raw_likelihood is None else int(raw_likelihood)
            impact = None if raw_impact is None else int(raw_impact)
            if likelihood is not None:
                likelihood = max(1, min(5, likelihood))
            if impact is not None:
                impact = max(1, min(5, impact))

            # Keep schema-safe known fields only.
            sanitized = {
                "recommendation_type": recommendation_type,
                "title": title,
                "rationale": rationale,
                "suggested_category": (
                    str(item.get("suggested_category")).strip() if item.get("suggested_category") is not None else None
                ),
                "suggested_likelihood": likelihood,
                "suggested_impact": impact,
                "suggested_treatment": (
                    str(item.get("suggested_treatment")).strip()
                    if item.get("suggested_treatment") is not None
                    else None
                ),
                "linked_risk_title": (
                    str(item.get("linked_risk_title")).strip() if item.get("linked_risk_title") is not None else None
                ),
            }

            normalized.append(sanitized)

        return normalized
