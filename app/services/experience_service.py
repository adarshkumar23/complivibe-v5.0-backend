from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.compliance_policy import CompliancePolicy
from app.models.control import Control
from app.models.issue import Issue
from app.models.obligation import Obligation
from app.models.risk import Risk
from app.models.task import Task
from app.models.vendor import Vendor
from app.schemas.experience import (
    CommandPaletteExecuteRequest,
    CommandPaletteExecuteResponse,
    CommandPaletteItem,
    CommandPaletteQueryResponse,
)
from app.services.audit_service import AuditService
from app.services.search_indexing_service import SearchIndexingService, SearchUnavailableError


ENTITY_NAVIGATION_PATHS: dict[str, str] = {
    "risk": "/risks/{id}",
    "control": "/controls/{id}",
    "vendor": "/vendors/{id}",
    "issue": "/issues/{id}",
    "compliance_policy": "/compliance-policies/{id}",
    "obligation": "/obligations/{id}",
}


ENTITY_MODEL_BY_TYPE: dict[str, type] = {
    "risk": Risk,
    "control": Control,
    "vendor": Vendor,
    "issue": Issue,
    "compliance_policy": CompliancePolicy,
    "obligation": Obligation,
}


class CommandPaletteService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _label_for_hit(hit: dict) -> str:
        for key in ("title", "name", "reference_code", "id"):
            value = str(hit.get(key) or "").strip()
            if value:
                return value
        return "Untitled"

    @staticmethod
    def _subtitle_for_hit(hit: dict) -> str:
        for key in ("description", "status", "severity", "policy_type", "category"):
            value = str(hit.get(key) or "").strip()
            if value:
                return value[:200]
        return ""

    def query(
        self,
        *,
        organization_id: uuid.UUID,
        query: str,
        entity_types: list[str] | None,
        limit: int,
    ) -> CommandPaletteQueryResponse:
        started = time.monotonic()
        try:
            raw = SearchIndexingService(self.db).search(
                query=query,
                organization_id=organization_id,
                entity_types=entity_types,
                limit=limit,
            )
        except SearchUnavailableError:
            raw = {"hits": [], "query": query, "took_ms": 0}

        items: list[CommandPaletteItem] = []
        for hit in raw.get("hits", []):
            entity_type = str(hit.get("entity_type") or "")
            entity_id = str(hit.get("id") or "")
            navigate_template = ENTITY_NAVIGATION_PATHS.get(entity_type)
            navigate_path = navigate_template.format(id=entity_id) if navigate_template else None
            items.append(
                CommandPaletteItem(
                    item_type="entity",
                    action_key="navigate_entity",
                    label=self._label_for_hit(hit),
                    subtitle=self._subtitle_for_hit(hit) or entity_type,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    navigate_path=navigate_path,
                    payload_hint={"entity_type": entity_type, "entity_id": entity_id},
                )
            )

        # Backend trigger action shortcut for fast task creation from Cmd+K.
        items.append(
            CommandPaletteItem(
                item_type="action",
                action_key="create_task",
                label=f"Create Task: {query.strip()}",
                subtitle="Create and assign a new follow-up task to yourself",
                navigate_path="/tasks",
                payload_hint={"title": query.strip()[:255]},
            )
        )
        took_ms = int((time.monotonic() - started) * 1000)
        return CommandPaletteQueryResponse(
            query=query,
            items=items[:limit],
            took_ms=max(took_ms, int(raw.get("took_ms") or 0)),
        )

    def _resolve_navigation_path(self, entity_type: str, entity_id: uuid.UUID | None) -> str | None:
        if not entity_id:
            return None
        template = ENTITY_NAVIGATION_PATHS.get(entity_type)
        if template is None:
            return None
        return template.format(id=str(entity_id))

    def _validate_entity_scope(self, organization_id: uuid.UUID, entity_type: str | None, entity_id: uuid.UUID | None) -> None:
        if not entity_type or not entity_id:
            return
        model = ENTITY_MODEL_BY_TYPE.get(entity_type)
        if model is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported entity_type")
        row = self.db.get(model, entity_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked entity not found")
        row_org_id = getattr(row, "organization_id", None)
        if row_org_id is not None and row_org_id != organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked entity not found")

    def execute(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        payload: CommandPaletteExecuteRequest,
    ) -> CommandPaletteExecuteResponse:
        now = self.utcnow()
        action_key = payload.action_key.strip().lower()
        if action_key == "navigate_entity":
            return CommandPaletteExecuteResponse(
                action_key=action_key,
                status="ok",
                navigate_path=self._resolve_navigation_path(payload.entity_type or "", payload.entity_id),
                executed_at=now,
            )

        if action_key == "create_task":
            title = str(payload.title or "").strip()
            if not title:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="title is required")
            self._validate_entity_scope(organization_id, payload.entity_type, payload.entity_id)
            row = Task(
                organization_id=organization_id,
                title=title[:255],
                description=str(payload.description or "").strip()[:4000] or None,
                status="open",
                priority="normal",
                task_type="general",
                owner_user_id=actor_user_id,
                created_by_user_id=actor_user_id,
                due_date=None,
                linked_entity_type=payload.entity_type,
                linked_entity_id=payload.entity_id,
                source="manual",
                reminder_status="none",
                metadata_json={"source": "command_palette"},
            )
            self.db.add(row)
            self.db.flush()
            self.audit.write_audit_log(
                action="command_palette.task_created",
                entity_type="task",
                entity_id=row.id,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                after_json={
                    "title": row.title,
                    "linked_entity_type": row.linked_entity_type,
                    "linked_entity_id": str(row.linked_entity_id) if row.linked_entity_id else None,
                },
                metadata_json={"source": "command_palette"},
            )
            return CommandPaletteExecuteResponse(
                action_key=action_key,
                status="ok",
                navigate_path=f"/tasks/{row.id}",
                task_id=row.id,
                executed_at=now,
            )

        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported action_key")
