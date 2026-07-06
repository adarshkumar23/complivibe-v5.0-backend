from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.compliance_deadline import ComplianceDeadline
from app.models.compliance_deadline_event import ComplianceDeadlineEvent
from app.models.compliance_policy import CompliancePolicy
from app.models.control import Control
from app.models.control_test_run import ControlTestRun
from app.models.evidence_item import EvidenceItem
from app.models.issue import Issue
from app.models.obligation import Obligation
from app.models.risk import Risk
from app.models.task import Task
from app.models.vendor import Vendor
from app.schemas.experience import (
    ComplianceTimelineEvent,
    ComplianceTimelineResponse,
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

TIMELINE_SCOPE_ENTITY_TYPES = {"evidence", "control", "risk", "issue", "deadline"}


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

    def compliance_timeline(
        self,
        *,
        organization_id: uuid.UUID,
        entity_type: str | None,
        entity_id: uuid.UUID | None,
        start_at: datetime | None,
        end_at: datetime | None,
        limit: int,
    ) -> ComplianceTimelineResponse:
        normalized_entity_type = (entity_type or "").strip().lower() or None
        if normalized_entity_type and normalized_entity_type not in TIMELINE_SCOPE_ENTITY_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported entity_type")
        if normalized_entity_type and entity_id is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="entity_id is required for entity-scoped timeline")
        if entity_id is not None and normalized_entity_type is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="entity_type is required when entity_id is provided")
        if start_at and end_at and start_at > end_at:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="start_at must be less than or equal to end_at")

        events: list[ComplianceTimelineEvent] = []

        if normalized_entity_type in {None, "evidence"}:
            evidence_stmt = select(EvidenceItem).where(EvidenceItem.organization_id == organization_id)
            if normalized_entity_type == "evidence" and entity_id:
                evidence_stmt = evidence_stmt.where(EvidenceItem.id == entity_id)
            if start_at:
                evidence_stmt = evidence_stmt.where(EvidenceItem.created_at >= start_at)
            if end_at:
                evidence_stmt = evidence_stmt.where(EvidenceItem.created_at <= end_at)
            evidence_rows = self.db.execute(evidence_stmt.order_by(EvidenceItem.created_at.desc()).limit(limit)).scalars().all()
            for row in evidence_rows:
                occurred_at = row.collected_at or row.created_at
                if start_at and occurred_at < start_at:
                    continue
                if end_at and occurred_at > end_at:
                    continue
                events.append(
                    ComplianceTimelineEvent(
                        event_key=f"evidence_collected:{row.id}",
                        event_type="evidence_collected",
                        occurred_at=occurred_at,
                        entity_type="evidence",
                        entity_id=row.id,
                        title=row.title,
                        status=row.review_status,
                        metadata={"evidence_type": row.evidence_type, "source": row.source},
                    )
                )

        if normalized_entity_type in {None, "control"}:
            test_stmt = select(ControlTestRun).where(ControlTestRun.organization_id == organization_id)
            if normalized_entity_type == "control" and entity_id:
                test_stmt = test_stmt.where(ControlTestRun.control_id == entity_id)
            if start_at:
                test_stmt = test_stmt.where(ControlTestRun.created_at >= start_at)
            if end_at:
                test_stmt = test_stmt.where(ControlTestRun.created_at <= end_at)
            test_rows = self.db.execute(test_stmt.order_by(ControlTestRun.created_at.desc()).limit(limit)).scalars().all()
            for row in test_rows:
                events.append(
                    ComplianceTimelineEvent(
                        event_key=f"control_tested:{row.id}",
                        event_type="control_tested",
                        occurred_at=row.created_at,
                        entity_type="control",
                        entity_id=row.control_id,
                        title=f"Control test {row.check_key}",
                        status=row.result,
                        metadata={"test_run_id": str(row.id), "execution_source": row.execution_source},
                    )
                )

        if normalized_entity_type in {None, "risk"}:
            risk_stmt = select(Risk).where(Risk.organization_id == organization_id)
            if normalized_entity_type == "risk" and entity_id:
                risk_stmt = risk_stmt.where(Risk.id == entity_id)
            if start_at:
                risk_stmt = risk_stmt.where(Risk.created_at >= start_at)
            if end_at:
                risk_stmt = risk_stmt.where(Risk.created_at <= end_at)
            risk_rows = self.db.execute(risk_stmt.order_by(Risk.created_at.desc()).limit(limit)).scalars().all()
            for row in risk_rows:
                events.append(
                    ComplianceTimelineEvent(
                        event_key=f"risk_raised:{row.id}",
                        event_type="risk_raised",
                        occurred_at=row.created_at,
                        entity_type="risk",
                        entity_id=row.id,
                        title=row.title,
                        status=row.status,
                        metadata={"severity": row.severity, "category": row.category},
                    )
                )

        if normalized_entity_type in {None, "issue"}:
            issue_stmt = select(Issue).where(and_(Issue.organization_id == organization_id, Issue.resolved_at.is_not(None)))
            if normalized_entity_type == "issue" and entity_id:
                issue_stmt = issue_stmt.where(Issue.id == entity_id)
            if start_at:
                issue_stmt = issue_stmt.where(Issue.resolved_at >= start_at)
            if end_at:
                issue_stmt = issue_stmt.where(Issue.resolved_at <= end_at)
            issue_rows = self.db.execute(issue_stmt.order_by(Issue.resolved_at.desc()).limit(limit)).scalars().all()
            for row in issue_rows:
                resolved_at = row.resolved_at
                if resolved_at is None:
                    continue
                events.append(
                    ComplianceTimelineEvent(
                        event_key=f"issue_resolved:{row.id}",
                        event_type="issue_resolved",
                        occurred_at=resolved_at,
                        entity_type="issue",
                        entity_id=row.id,
                        title=row.title,
                        status=row.status,
                        metadata={"severity": row.severity, "issue_type": row.issue_type},
                    )
                )

        met_stmt = select(ComplianceDeadline).where(
            and_(
                ComplianceDeadline.organization_id == organization_id,
                ComplianceDeadline.status == "completed",
                ComplianceDeadline.completed_at.is_not(None),
            )
        )
        if normalized_entity_type == "deadline" and entity_id:
            met_stmt = met_stmt.where(ComplianceDeadline.id == entity_id)
        if normalized_entity_type and normalized_entity_type != "deadline" and entity_id:
            met_stmt = met_stmt.where(
                and_(
                    ComplianceDeadline.linked_entity_type == normalized_entity_type,
                    ComplianceDeadline.linked_entity_id == entity_id,
                )
            )
        if start_at:
            met_stmt = met_stmt.where(ComplianceDeadline.completed_at >= start_at)
        if end_at:
            met_stmt = met_stmt.where(ComplianceDeadline.completed_at <= end_at)
        met_rows = self.db.execute(met_stmt.order_by(ComplianceDeadline.completed_at.desc()).limit(limit)).scalars().all()
        for row in met_rows:
            if row.completed_at is None:
                continue
            completed_on_time = row.completed_at.date() <= row.due_date
            event_type = "deadline_met" if completed_on_time else "deadline_missed"
            events.append(
                ComplianceTimelineEvent(
                    event_key=f"{event_type}:{row.id}:{row.completed_at.isoformat()}",
                    event_type=event_type,
                    occurred_at=row.completed_at,
                    entity_type="deadline",
                    entity_id=row.id,
                    title=row.title,
                    status=row.status,
                    metadata={"due_date": row.due_date.isoformat(), "completed_on_time": completed_on_time},
                )
            )

        missed_stmt = (
            select(ComplianceDeadlineEvent, ComplianceDeadline)
            .join(ComplianceDeadline, ComplianceDeadline.id == ComplianceDeadlineEvent.deadline_id)
            .where(
                and_(
                    ComplianceDeadlineEvent.organization_id == organization_id,
                    ComplianceDeadlineEvent.event_type == "overdue_detected",
                    ComplianceDeadlineEvent.dry_run.is_(False),
                )
            )
        )
        if normalized_entity_type == "deadline" and entity_id:
            missed_stmt = missed_stmt.where(ComplianceDeadline.id == entity_id)
        if normalized_entity_type and normalized_entity_type != "deadline" and entity_id:
            missed_stmt = missed_stmt.where(
                and_(
                    ComplianceDeadline.linked_entity_type == normalized_entity_type,
                    ComplianceDeadline.linked_entity_id == entity_id,
                )
            )
        if start_at:
            missed_stmt = missed_stmt.where(ComplianceDeadlineEvent.created_at >= start_at)
        if end_at:
            missed_stmt = missed_stmt.where(ComplianceDeadlineEvent.created_at <= end_at)
        missed_rows = self.db.execute(missed_stmt.order_by(ComplianceDeadlineEvent.created_at.desc()).limit(limit)).all()
        for event_row, deadline in missed_rows:
            events.append(
                ComplianceTimelineEvent(
                    event_key=f"deadline_missed:{event_row.id}",
                    event_type="deadline_missed",
                    occurred_at=event_row.created_at,
                    entity_type="deadline",
                    entity_id=deadline.id,
                    title=deadline.title,
                    status=deadline.status,
                    metadata={"due_date": deadline.due_date.isoformat(), "event_type": event_row.event_type},
                )
            )

        events.sort(key=lambda item: item.occurred_at, reverse=True)
        trimmed = events[:limit]
        return ComplianceTimelineResponse(total_events=len(trimmed), events=trimmed)
