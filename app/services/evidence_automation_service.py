import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.evidence_automation_rule import EvidenceAutomationRule
from app.models.evidence_item import EvidenceItem
from app.services.evidence_service import EvidenceService

PLACEHOLDER_PATTERN = re.compile(r"\{\{([^{}]+)\}\}")


class EvidenceAutomationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.evidence_service = EvidenceService(db)

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _resolve_path(payload: dict[str, Any], path: str) -> Any:
        current: Any = payload
        for segment in [p for p in path.split(".") if p]:
            if isinstance(current, dict) and segment in current:
                current = current[segment]
                continue
            return None
        return current

    @classmethod
    def _render_template(cls, template: str, payload: dict[str, Any]) -> str:
        def _replace(match: re.Match[str]) -> str:
            value = cls._resolve_path(payload, match.group(1).strip())
            if value is None:
                return ""
            return str(value)

        return PLACEHOLDER_PATTERN.sub(_replace, template).strip()

    @classmethod
    def _matches_rule(cls, *, payload: dict[str, Any], trigger_config: dict[str, Any]) -> bool:
        cls.validate_trigger_config(trigger_config)
        required_fields = trigger_config.get("required_fields") or []
        for key in required_fields:
            if cls._resolve_path(payload, key) is None:
                return False

        match_cfg = trigger_config.get("match") or {}
        for key, expected in match_cfg.items():
            if cls._resolve_path(payload, str(key)) != expected:
                return False
        return True

    @classmethod
    def _parse_transform_template(cls, template: str | None) -> dict[str, Any]:
        if template is None or not template.strip():
            return {}
        raw = template.strip()
        if raw.startswith("{"):
            loaded = json.loads(raw)
            if not isinstance(loaded, dict):
                raise ValueError("transform_template JSON must be an object")
            parsed = loaded
        else:
            parsed = {"title": raw}

        title_template = parsed.get("title")
        if title_template is not None and not isinstance(title_template, str):
            raise ValueError("transform_template.title must be a string")
        description_template = parsed.get("description")
        if description_template is not None and not isinstance(description_template, str):
            raise ValueError("transform_template.description must be a string")
        link_template = parsed.get("external_reference_url")
        if link_template is not None and not isinstance(link_template, str):
            raise ValueError("transform_template.external_reference_url must be a string")
        valid_until_days = parsed.get("valid_until_days")
        if valid_until_days is not None and not isinstance(valid_until_days, int):
            raise ValueError("transform_template.valid_until_days must be an integer")
        metadata = parsed.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("transform_template.metadata must be an object")
        return parsed

    def _apply_transform(
        self,
        *,
        rule: EvidenceAutomationRule,
        payload: dict[str, Any],
        received_at: datetime | None,
    ) -> dict[str, Any]:
        parsed_template = self._parse_transform_template(rule.transform_template)
        default_title = f"Automated evidence ({rule.trigger_source}) {self._utc_now().isoformat()}"

        title_template = parsed_template.get("title")
        description_template = parsed_template.get("description")
        link_template = parsed_template.get("external_reference_url")
        valid_until_days = parsed_template.get("valid_until_days")

        metadata: dict[str, Any] = {
            "trigger_source": rule.trigger_source,
            "automation_rule_id": str(rule.id),
            "ingest_payload": payload,
        }
        metadata_template = parsed_template.get("metadata")
        if metadata_template is not None:
            for key, value in metadata_template.items():
                if isinstance(value, str):
                    metadata[str(key)] = self._render_template(value, payload)
                else:
                    metadata[str(key)] = value

        valid_until = None
        if valid_until_days is not None:
            base = received_at or self._utc_now()
            valid_until = base + timedelta(days=valid_until_days)

        return {
            "title": self._render_template(title_template, payload) if title_template else default_title,
            "description": self._render_template(description_template, payload) if description_template else None,
            "external_reference_url": self._render_template(link_template, payload) if link_template else None,
            "collected_at": received_at or self._utc_now(),
            "valid_until": valid_until,
            "metadata_json": metadata,
        }

    def create_rule(
        self,
        *,
        organization_id: uuid.UUID,
        created_by_user_id: uuid.UUID | None,
        trigger_source: str,
        trigger_config: dict[str, Any],
        target_control_id: uuid.UUID | None,
        evidence_type: str,
        transform_template: str | None,
        is_active: bool,
    ) -> EvidenceAutomationRule:
        if target_control_id is not None:
            self.evidence_service.require_control_in_org(organization_id, target_control_id)
        try:
            self.validate_trigger_config(trigger_config or {})
            self._parse_transform_template(transform_template)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        row = EvidenceAutomationRule(
            organization_id=organization_id,
            trigger_source=trigger_source,
            trigger_config=trigger_config or {},
            target_control_id=target_control_id,
            evidence_type=evidence_type,
            transform_template=transform_template,
            is_active=is_active,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_rules(self, organization_id: uuid.UUID) -> list[EvidenceAutomationRule]:
        return (
            self.db.execute(
                select(EvidenceAutomationRule)
                .where(EvidenceAutomationRule.organization_id == organization_id)
                .order_by(EvidenceAutomationRule.created_at.desc())
            )
            .scalars()
            .all()
        )

    def get_rule(self, organization_id: uuid.UUID, rule_id: uuid.UUID) -> EvidenceAutomationRule:
        row = (
            self.db.execute(
                select(EvidenceAutomationRule).where(
                    EvidenceAutomationRule.organization_id == organization_id,
                    EvidenceAutomationRule.id == rule_id,
                )
            )
            .scalars()
            .one_or_none()
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence automation rule not found")
        return row

    def ingest(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        source: str,
        payload: dict[str, Any],
        received_at: datetime | None = None,
        request_ip: str | None = None,
        request_user_agent: str | None = None,
    ) -> tuple[list[EvidenceItem], list[tuple[uuid.UUID, str]], int]:
        rules = (
            self.db.execute(
                select(EvidenceAutomationRule).where(
                    EvidenceAutomationRule.organization_id == organization_id,
                    EvidenceAutomationRule.trigger_source == source,
                    EvidenceAutomationRule.is_active.is_(True),
                )
            )
            .scalars()
            .all()
        )

        created: list[EvidenceItem] = []
        errors: list[tuple[uuid.UUID, str]] = []
        skipped = 0
        for rule in rules:
            try:
                if not self._matches_rule(payload=payload, trigger_config=rule.trigger_config or {}):
                    skipped += 1
                    continue
                transformed = self._apply_transform(rule=rule, payload=payload, received_at=received_at)
                evidence, _ = self.evidence_service.create_evidence_item(
                    organization_id=organization_id,
                    actor_user_id=actor_user_id,
                    title=transformed["title"],
                    description=transformed["description"],
                    evidence_type=rule.evidence_type,
                    source=f"automation_{source}",
                    external_reference_url=transformed["external_reference_url"],
                    collected_at=transformed["collected_at"],
                    valid_until=transformed["valid_until"],
                    metadata_json=transformed["metadata_json"],
                    target_control_id=rule.target_control_id,
                    link_confidence="imported",
                    link_rationale="Linked by evidence automation rule",
                    request_ip=request_ip,
                    request_user_agent=request_user_agent,
                    audit_metadata={"source": f"automation_{source}", "automation_rule_id": str(rule.id)},
                )
                created.append(evidence)
            except Exception as exc:  # noqa: BLE001 - collect per-rule errors without failing other rules
                errors.append((rule.id, str(exc)))
        return created, errors, skipped
    @classmethod
    def validate_trigger_config(cls, trigger_config: dict[str, Any]) -> None:
        if not isinstance(trigger_config, dict):
            raise ValueError("trigger_config must be an object")
        required_fields = trigger_config.get("required_fields") or []
        if not isinstance(required_fields, list):
            raise ValueError("trigger_config.required_fields must be a list when provided")
        for key in required_fields:
            if not isinstance(key, str):
                raise ValueError("trigger_config.required_fields must only include strings")
        match_cfg = trigger_config.get("match") or {}
        if not isinstance(match_cfg, dict):
            raise ValueError("trigger_config.match must be an object when provided")
