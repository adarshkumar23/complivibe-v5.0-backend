import hashlib
import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.control import Control
from app.models.evidence_automation_rule import EvidenceAutomationIngestEvent, EvidenceAutomationRule
from app.models.evidence_item import EvidenceItem
from app.services.evidence_service import EvidenceService

PLACEHOLDER_PATTERN = re.compile(r"\{\{([^{}]+)\}\}")

# A rule that hasn't successfully fired in this many days (while active) is
# considered stale/possibly-broken and is flagged in rule reads.
STALE_RULE_THRESHOLD_DAYS = 14
# Consecutive ingest errors at/above this count flag a rule as needing attention.
NEEDS_ATTENTION_ERROR_THRESHOLD = 3


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
    def _resolve_idempotency_key(cls, *, payload: dict[str, Any], trigger_config: dict[str, Any]) -> str | None:
        """Resolve a dedupe key for this ingest event from trigger_config.idempotency_key_path,
        if configured. Returns None when no path is configured or the path resolves to nothing,
        in which case no dedupe is attempted (matches prior behavior)."""
        key_path = trigger_config.get("idempotency_key_path")
        if not key_path or not isinstance(key_path, str):
            return None
        value = cls._resolve_path(payload, key_path)
        if value is None:
            return None
        return str(value)

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

    # Fields an inbound webhook/email/form payload may use to carry the checksum of the
    # actual underlying document/attachment. Checked in order; first match wins.
    _CHECKSUM_PAYLOAD_KEYS = ("checksum_sha256", "sha256", "file_checksum_sha256", "content_checksum_sha256")

    @classmethod
    def _compute_checksum(cls, payload: dict[str, Any]) -> str:
        """Content-based fingerprint for an ingested evidence payload. If the source
        system already tells us the document's checksum (common for webhook/email/form
        integrations that forward a hash of the attached file), use that directly so two
        deliveries of the same document dedupe correctly. Otherwise fall back to hashing
        the canonical (sorted-key) JSON of the whole payload, so a byte-identical
        resubmission of the same event is still recognized as a duplicate."""
        for key in cls._CHECKSUM_PAYLOAD_KEYS:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        canonical = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

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

        # Note: an explicit title_template that renders to an empty string (e.g. a
        # placeholder path that doesn't exist in the payload) is intentionally left as
        # empty here rather than silently falling back to default_title -- it surfaces
        # as create_evidence_item's "title is required" error, which is how a
        # misconfigured rule's consecutive_error_count/needs_attention flag gets set.
        title = self._render_template(title_template, payload) if title_template else default_title

        file_name = payload.get("file_name") if isinstance(payload.get("file_name"), str) else None
        mime_type = payload.get("mime_type") if isinstance(payload.get("mime_type"), str) else None
        size_bytes = payload.get("size_bytes") if isinstance(payload.get("size_bytes"), int) else None

        return {
            "title": title,
            "description": self._render_template(description_template, payload) if description_template else None,
            "external_reference_url": self._render_template(link_template, payload) if link_template else None,
            "collected_at": received_at or self._utc_now(),
            "valid_until": valid_until,
            "metadata_json": metadata,
            "checksum_sha256": self._compute_checksum(payload),
            "file_name": file_name,
            "mime_type": mime_type,
            "size_bytes": size_bytes,
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

    @staticmethod
    def _as_aware(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    def describe_rule_health(self, rule: EvidenceAutomationRule) -> dict[str, Any]:
        """Compute context flags for a rule so admins can see, at a glance, whether an
        evidence connector has gone dark (stale), is repeatedly failing (needs_attention),
        or points at a control that no longer exists / has been archived."""
        flags: list[str] = []
        now = self._utc_now()

        is_stale = False
        if rule.is_active:
            reference = self._as_aware(rule.last_triggered_at)
            created_at = self._as_aware(rule.created_at)
            if reference is None:
                # never fired: only stale once the rule has existed long enough that a
                # freshly-created rule with a delayed first delivery isn't immediately flagged.
                if created_at is not None and (now - created_at) > timedelta(days=STALE_RULE_THRESHOLD_DAYS):
                    is_stale = True
            elif (now - reference) > timedelta(days=STALE_RULE_THRESHOLD_DAYS):
                is_stale = True
        if is_stale:
            flags.append("stale_connector")

        needs_attention = (rule.consecutive_error_count or 0) >= NEEDS_ATTENTION_ERROR_THRESHOLD
        if needs_attention:
            flags.append("repeated_ingest_failures")

        target_control_archived = False
        if rule.target_control_id is not None:
            control = self.db.execute(
                select(Control).where(Control.id == rule.target_control_id)
            ).scalar_one_or_none()
            if control is None:
                flags.append("target_control_missing")
            elif control.status == "archived":
                target_control_archived = True
                flags.append("target_control_archived")

        return {
            "is_stale": is_stale,
            "needs_attention": needs_attention,
            "target_control_archived": target_control_archived,
            "context_flags": flags,
        }

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
    ) -> tuple[list[EvidenceItem], list[tuple[uuid.UUID, str]], int, list[tuple[uuid.UUID, str]]]:
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
        duplicates: list[tuple[uuid.UUID, str]] = []
        skipped = 0
        now = self._utc_now()
        for rule in rules:
            trigger_config = rule.trigger_config or {}
            if not self._matches_rule(payload=payload, trigger_config=trigger_config):
                skipped += 1
                continue

            idempotency_key = self._resolve_idempotency_key(payload=payload, trigger_config=trigger_config)
            rule.last_matched_at = now

            if idempotency_key is not None:
                existing = self.db.execute(
                    select(EvidenceAutomationIngestEvent).where(
                        EvidenceAutomationIngestEvent.automation_rule_id == rule.id,
                        EvidenceAutomationIngestEvent.idempotency_key == idempotency_key,
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    duplicates.append((rule.id, idempotency_key))
                    continue

            try:
                with self.db.begin_nested():
                    transformed = self._apply_transform(rule=rule, payload=payload, received_at=received_at)
                    evidence, _, is_content_duplicate = self.evidence_service.create_evidence_item(
                        organization_id=organization_id,
                        actor_user_id=actor_user_id,
                        title=transformed["title"],
                        description=transformed["description"],
                        evidence_type=rule.evidence_type,
                        source=f"automation_{source}",
                        file_name=transformed["file_name"],
                        mime_type=transformed["mime_type"],
                        size_bytes=transformed["size_bytes"],
                        checksum_sha256=transformed["checksum_sha256"],
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
                    self.db.add(
                        EvidenceAutomationIngestEvent(
                            organization_id=organization_id,
                            automation_rule_id=rule.id,
                            source=source,
                            idempotency_key=idempotency_key,
                            status="duplicate" if is_content_duplicate else "created",
                            evidence_item_id=evidence.id,
                        )
                    )
                    self.db.flush()
                if is_content_duplicate:
                    duplicates.append((rule.id, idempotency_key or transformed["checksum_sha256"]))
                    rule.last_matched_at = now
                    continue
                created.append(evidence)
                rule.last_triggered_at = now
                rule.trigger_count = (rule.trigger_count or 0) + 1
                rule.consecutive_error_count = 0
            except IntegrityError:
                # Concurrent retry of the same event raced us to the unique
                # (rule_id, idempotency_key) index - treat as a duplicate, not an error.
                if idempotency_key is not None:
                    duplicates.append((rule.id, idempotency_key))
            except Exception as exc:  # noqa: BLE001 - collect per-rule errors without failing other rules
                errors.append((rule.id, str(exc)))
                rule.consecutive_error_count = (rule.consecutive_error_count or 0) + 1
                rule.last_error_at = now
                rule.last_error_message = str(exc)[:2000]
                self.db.add(
                    EvidenceAutomationIngestEvent(
                        organization_id=organization_id,
                        automation_rule_id=rule.id,
                        source=source,
                        idempotency_key=idempotency_key,
                        status="error",
                        error_message=str(exc)[:2000],
                    )
                )
                self.db.flush()
        self.db.flush()
        return created, errors, skipped, duplicates
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
        idempotency_key_path = trigger_config.get("idempotency_key_path")
        if idempotency_key_path is not None and not isinstance(idempotency_key_path, str):
            raise ValueError("trigger_config.idempotency_key_path must be a string when provided")
