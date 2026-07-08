import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import and_, func, not_, or_, select
from sqlalchemy.orm import Session

from app.models.automation_action_log import AutomationActionLog
from app.models.automation_rule import AutomationRule
from app.models.automation_rule_execution import AutomationRuleExecution
from app.models.automation_rule_version import AutomationRuleVersion
from app.models.control import Control
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.organization_obligation_state import OrganizationObligationState
from app.models.risk import Risk
from app.models.risk_control_link import RiskControlLink
from app.models.task import Task
from app.models.user import User
from app.services.seed_service import SeedService
from app.services.task_service import TaskService
from app.core.validation import validate_choice

ALLOWED_CONDITION_TYPES = {
    "risk_critical_without_control",
    "risk_without_owner",
    "risk_review_overdue",
    "control_without_evidence",
    "control_needs_review",
    "evidence_expired",
    "evidence_needs_review",
    "obligation_applicable_without_control",
    "task_overdue",
}

ALLOWED_ACTION_TYPES = {
    "create_task",
    "queue_email_reminder",
    "create_task_and_queue_email",
}

ALLOWED_SCHEDULE_CADENCE = {"hourly", "daily", "weekly", "monthly"}
AUTOMATION_STALE_RULE_HOURS = 24 * 7
AUTOMATION_STALLED_SCHEDULE_HOURS = 24


class AutomationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _to_utc(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)

    @staticmethod
    def validate_rule_types(condition_type: str, action_type: str) -> None:
        condition_type = validate_choice(condition_type, ALLOWED_CONDITION_TYPES, "condition_type", status_code=status.HTTP_400_BAD_REQUEST)
        action_type = validate_choice(action_type, ALLOWED_ACTION_TYPES, "action_type", status_code=status.HTTP_400_BAD_REQUEST)
    @staticmethod
    def validate_schedule_cadence(cadence: str | None) -> None:
        if cadence is None:
            return
        cadence = validate_choice(cadence, ALLOWED_SCHEDULE_CADENCE, "schedule_cadence", status_code=status.HTTP_400_BAD_REQUEST)
    @staticmethod
    def build_idempotency_key(
        *,
        organization_id: uuid.UUID,
        rule_id: uuid.UUID,
        rule_version: int,
        condition_type: str,
        action_type: str,
        entity_type: str,
        entity_id: uuid.UUID,
    ) -> str:
        return f"automation:{organization_id}:{rule_id}:v{rule_version}:{condition_type}:{action_type}:{entity_type}:{entity_id}"

    def _existing_created_action(self, organization_id: uuid.UUID, idempotency_key: str) -> AutomationActionLog | None:
        return self.db.execute(
            select(AutomationActionLog).where(
                AutomationActionLog.organization_id == organization_id,
                AutomationActionLog.idempotency_key == idempotency_key,
                AutomationActionLog.action_status == "created",
            )
        ).scalar_one_or_none()

    def _log_action(
        self,
        *,
        organization_id: uuid.UUID,
        rule_id: uuid.UUID,
        execution_id: uuid.UUID,
        entity_type: str,
        entity_id: uuid.UUID,
        action_type: str,
        action_status: str,
        idempotency_key: str,
        created_task_id: uuid.UUID | None = None,
        created_email_outbox_id: uuid.UUID | None = None,
        skipped_reason: str | None = None,
        error_message: str | None = None,
    ) -> AutomationActionLog:
        row = AutomationActionLog(
            organization_id=organization_id,
            rule_id=rule_id,
            execution_id=execution_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action_type=action_type,
            action_status=action_status,
            idempotency_key=idempotency_key,
            created_task_id=created_task_id,
            created_email_outbox_id=created_email_outbox_id,
            skipped_reason=skipped_reason,
            error_message=error_message,
            created_at=self.now(),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _schedule_config_json(self, rule: AutomationRule) -> dict:
        return {
            "schedule_enabled": rule.schedule_enabled,
            "schedule_cadence": rule.schedule_cadence,
            "schedule_timezone": rule.schedule_timezone,
            "schedule_start_at": rule.schedule_start_at.isoformat() if rule.schedule_start_at else None,
            "schedule_end_at": rule.schedule_end_at.isoformat() if rule.schedule_end_at else None,
            "schedule_window_start": rule.schedule_window_start,
            "schedule_window_end": rule.schedule_window_end,
            "next_run_at": rule.next_run_at.isoformat() if rule.next_run_at else None,
            "last_scheduled_run_at": rule.last_scheduled_run_at.isoformat() if rule.last_scheduled_run_at else None,
            "last_dry_run_at": rule.last_dry_run_at.isoformat() if rule.last_dry_run_at else None,
            "run_mode": rule.run_mode,
        }

    def rule_payload(self, *, rule: AutomationRule, now: datetime | None = None) -> dict:
        now = self._to_utc(now) or self.now()
        last_run_at = self._to_utc(rule.last_run_at)
        hours_since_last_run = None
        if last_run_at is not None:
            hours_since_last_run = round(max(0.0, (now - last_run_at).total_seconds() / 3600.0), 3)
        schedule_overdue = bool(
            rule.status == "active"
            and rule.trigger_type == "scheduled_placeholder"
            and rule.schedule_enabled
            and rule.next_run_at is not None
            and (self._to_utc(rule.next_run_at) or now) <= now
        )
        schedule_drift_minutes = None
        if schedule_overdue and rule.next_run_at is not None:
            schedule_drift_minutes = round(max(0.0, (now - (self._to_utc(rule.next_run_at) or now)).total_seconds() / 60.0), 3)
        stale_rule = bool(
            rule.status == "active"
            and hours_since_last_run is not None
            and hours_since_last_run >= AUTOMATION_STALE_RULE_HOURS
        )
        context_flags: list[str] = []
        if rule.status != "active":
            context_flags.append("rule_inactive")
        if stale_rule:
            context_flags.append("stale_rule")
        if rule.trigger_type == "scheduled_placeholder" and rule.schedule_enabled:
            context_flags.append("scheduled_rule")
        if schedule_overdue:
            context_flags.append("schedule_overdue")
        if rule.run_mode == "dry_run":
            context_flags.append("dry_run_mode")
        return {
            "id": rule.id,
            "organization_id": rule.organization_id,
            "name": rule.name,
            "description": rule.description,
            "trigger_type": rule.trigger_type,
            "condition_type": rule.condition_type,
            "condition_config_json": rule.condition_config_json,
            "action_type": rule.action_type,
            "action_config_json": rule.action_config_json,
            "status": rule.status,
            "priority": rule.priority,
            "last_run_at": rule.last_run_at,
            "schedule_enabled": bool(rule.schedule_enabled),
            "schedule_cadence": rule.schedule_cadence,
            "schedule_timezone": rule.schedule_timezone,
            "schedule_start_at": rule.schedule_start_at,
            "schedule_end_at": rule.schedule_end_at,
            "schedule_window_start": rule.schedule_window_start,
            "schedule_window_end": rule.schedule_window_end,
            "next_run_at": rule.next_run_at,
            "last_scheduled_run_at": rule.last_scheduled_run_at,
            "last_dry_run_at": rule.last_dry_run_at,
            "run_mode": rule.run_mode,
            "version": int(rule.version),
            "version_notes": rule.version_notes,
            "created_by_user_id": rule.created_by_user_id,
            "stale_rule": stale_rule,
            "hours_since_last_run": hours_since_last_run,
            "schedule_overdue": schedule_overdue,
            "schedule_drift_minutes": schedule_drift_minutes,
            "context_flags": context_flags,
            "created_at": rule.created_at,
            "updated_at": rule.updated_at,
        }

    def execution_payload(self, *, execution: AutomationRuleExecution, now: datetime | None = None) -> dict:
        now = self._to_utc(now) or self.now()
        started_at = self._to_utc(execution.started_at) or now
        finished_at = self._to_utc(execution.finished_at)
        duration_seconds = None
        if finished_at is not None:
            duration_seconds = round(max(0.0, (finished_at - started_at).total_seconds()), 3)
        elif execution.status == "running":
            duration_seconds = round(max(0.0, (now - started_at).total_seconds()), 3)
        success_ratio = 0.0
        if execution.matched_count > 0:
            success_ratio = round(max(0.0, min(1.0, float(execution.action_count) / float(execution.matched_count))), 4)
        had_errors = bool(execution.error_count > 0 or execution.status in {"failed", "completed_with_errors"})
        context_flags: list[str] = []
        if execution.dry_run:
            context_flags.append("dry_run_execution")
        if execution.matched_count == 0:
            context_flags.append("no_matches")
        if execution.skipped_count > 0:
            context_flags.append("contains_skips")
        if had_errors:
            context_flags.append("contains_errors")
        if execution.trigger_source == "scheduled_due_run":
            context_flags.append("scheduled_execution")
        return {
            "id": execution.id,
            "organization_id": execution.organization_id,
            "rule_id": execution.rule_id,
            "status": execution.status,
            "started_at": execution.started_at,
            "finished_at": execution.finished_at,
            "matched_count": int(execution.matched_count),
            "action_count": int(execution.action_count),
            "skipped_count": int(execution.skipped_count),
            "error_count": int(execution.error_count),
            "idempotency_key": execution.idempotency_key,
            "trigger_source": execution.trigger_source,
            "dry_run": bool(execution.dry_run),
            "rule_version": execution.rule_version,
            "scheduled_run_at": execution.scheduled_run_at,
            "idempotency_scope": execution.idempotency_scope,
            "summary_json": execution.summary_json,
            "created_by_user_id": execution.created_by_user_id,
            "duration_seconds": duration_seconds,
            "success_ratio": success_ratio,
            "had_errors": had_errors,
            "context_flags": context_flags,
            "created_at": execution.created_at,
            "updated_at": execution.updated_at,
        }

    def create_rule_version_snapshot(self, *, rule: AutomationRule, actor_user_id: uuid.UUID | None, version_notes: str | None) -> AutomationRuleVersion:
        row = AutomationRuleVersion(
            organization_id=rule.organization_id,
            rule_id=rule.id,
            version=rule.version,
            name=rule.name,
            description=rule.description,
            trigger_type=rule.trigger_type,
            condition_type=rule.condition_type,
            condition_config_json=rule.condition_config_json,
            action_type=rule.action_type,
            action_config_json=rule.action_config_json,
            schedule_config_json=self._schedule_config_json(rule),
            status=rule.status,
            version_notes=version_notes,
            created_by_user_id=actor_user_id,
            created_at=self.now(),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def calculate_next_run_at(self, *, cadence: str | None, base_time: datetime | None = None) -> datetime | None:
        if cadence is None:
            return None
        now = self.now()
        base = self._to_utc(base_time) or now
        if cadence == "hourly":
            return base + timedelta(hours=1)
        if cadence == "daily":
            return base + timedelta(days=1)
        if cadence == "weekly":
            return base + timedelta(days=7)
        if cadence == "monthly":
            return base + timedelta(days=30)
        return None

    def is_within_execution_window(self, rule: AutomationRule, now: datetime | None = None) -> bool:
        if not rule.schedule_window_start or not rule.schedule_window_end:
            return True
        now = now or self.now()
        now_hm = now.strftime("%H:%M")
        start = rule.schedule_window_start
        end = rule.schedule_window_end

        if start <= end:
            return start <= now_hm <= end
        return now_hm >= start or now_hm <= end

    def is_rule_due(self, rule: AutomationRule, now: datetime | None = None) -> bool:
        now = self._to_utc(now) or self.now()
        next_run_at = self._to_utc(rule.next_run_at)
        schedule_start_at = self._to_utc(rule.schedule_start_at)
        schedule_end_at = self._to_utc(rule.schedule_end_at)
        if rule.status != "active":
            return False
        if rule.trigger_type != "scheduled_placeholder":
            return False
        if not rule.schedule_enabled:
            return False
        if next_run_at is None:
            return False
        if schedule_start_at and now < schedule_start_at:
            return False
        if schedule_end_at and now > schedule_end_at:
            return False
        if next_run_at > now:
            return False
        if not self.is_within_execution_window(rule, now):
            return False
        return True

    def due_scheduled_rules(self, organization_id: uuid.UUID, *, limit: int = 25) -> list[AutomationRule]:
        now = self.now()
        rows = self.db.execute(
            select(AutomationRule)
            .where(
                AutomationRule.organization_id == organization_id,
                AutomationRule.status == "active",
                AutomationRule.trigger_type == "scheduled_placeholder",
                AutomationRule.schedule_enabled.is_(True),
                AutomationRule.next_run_at.is_not(None),
                AutomationRule.next_run_at <= now,
            )
            .order_by(AutomationRule.next_run_at.asc())
            .limit(limit)
        ).scalars().all()
        return [r for r in rows if self.is_rule_due(r, now)]

    def match_entities(self, organization_id: uuid.UUID, condition_type: str) -> list[dict]:
        now = self.now()
        if condition_type == "risk_critical_without_control":
            rows = self.db.execute(
                select(Risk).where(
                    Risk.organization_id == organization_id,
                    Risk.status != "archived",
                    Risk.severity == "critical",
                    not_(
                        Risk.id.in_(
                            select(RiskControlLink.risk_id).where(
                                RiskControlLink.organization_id == organization_id,
                                RiskControlLink.status == "active",
                            )
                        )
                    ),
                )
            ).scalars().all()
            return [{"entity_type": "risk", "entity_id": r.id, "title": r.title, "owner_user_id": r.owner_user_id} for r in rows]

        if condition_type == "risk_without_owner":
            rows = self.db.execute(
                select(Risk).where(
                    Risk.organization_id == organization_id,
                    Risk.status != "archived",
                    Risk.owner_user_id.is_(None),
                )
            ).scalars().all()
            return [{"entity_type": "risk", "entity_id": r.id, "title": r.title, "owner_user_id": None} for r in rows]

        if condition_type == "risk_review_overdue":
            rows = self.db.execute(
                select(Risk).where(
                    Risk.organization_id == organization_id,
                    Risk.status != "archived",
                    Risk.review_due_at.is_not(None),
                    Risk.review_due_at < now,
                )
            ).scalars().all()
            return [{"entity_type": "risk", "entity_id": r.id, "title": r.title, "owner_user_id": r.owner_user_id} for r in rows]

        if condition_type == "control_without_evidence":
            rows = self.db.execute(
                select(Control).where(
                    Control.organization_id == organization_id,
                    Control.status != "archived",
                    not_(
                        Control.id.in_(
                            select(EvidenceControlLink.control_id).where(
                                EvidenceControlLink.organization_id == organization_id,
                                EvidenceControlLink.link_status == "active",
                            )
                        )
                    ),
                )
            ).scalars().all()
            return [{"entity_type": "control", "entity_id": c.id, "title": c.title, "owner_user_id": c.owner_user_id} for c in rows]

        if condition_type == "control_needs_review":
            rows = self.db.execute(
                select(Control).where(
                    Control.organization_id == organization_id,
                    Control.status == "needs_review",
                )
            ).scalars().all()
            return [{"entity_type": "control", "entity_id": c.id, "title": c.title, "owner_user_id": c.owner_user_id} for c in rows]

        if condition_type == "evidence_expired":
            rows = self.db.execute(
                select(EvidenceItem).where(
                    EvidenceItem.organization_id == organization_id,
                    EvidenceItem.status == "active",
                    EvidenceItem.freshness_status == "expired",
                )
            ).scalars().all()
            return [{"entity_type": "evidence", "entity_id": e.id, "title": e.title, "owner_user_id": e.uploaded_by_user_id} for e in rows]

        if condition_type == "evidence_needs_review":
            rows = self.db.execute(
                select(EvidenceItem).where(
                    EvidenceItem.organization_id == organization_id,
                    EvidenceItem.status == "active",
                    EvidenceItem.review_status.in_(["not_reviewed", "needs_review"]),
                )
            ).scalars().all()
            return [{"entity_type": "evidence", "entity_id": e.id, "title": e.title, "owner_user_id": e.uploaded_by_user_id} for e in rows]

        if condition_type == "obligation_applicable_without_control":
            states = self.db.execute(
                select(OrganizationObligationState).where(
                    OrganizationObligationState.organization_id == organization_id,
                    OrganizationObligationState.applicability_status == "applicable",
                    not_(
                        OrganizationObligationState.obligation_id.in_(
                            select(ControlObligationMapping.obligation_id).where(
                                ControlObligationMapping.organization_id == organization_id,
                                ControlObligationMapping.status == "active",
                            )
                        )
                    ),
                )
            ).scalars().all()
            return [{"entity_type": "obligation", "entity_id": st.obligation_id, "title": f"Obligation {st.obligation_id}", "owner_user_id": st.owner_user_id} for st in states]

        if condition_type == "task_overdue":
            rows = self.db.execute(
                select(Task).where(
                    Task.organization_id == organization_id,
                    Task.status.in_(["open", "in_progress", "blocked"]),
                    Task.due_date.is_not(None),
                    Task.due_date < now,
                )
            ).scalars().all()
            return [{"entity_type": "task", "entity_id": t.id, "title": t.title, "owner_user_id": t.owner_user_id} for t in rows]

        return []

    @staticmethod
    def _task_type_for_entity(entity_type: str) -> str:
        return {
            "risk": "risk_treatment",
            "control": "control_remediation",
            "evidence": "evidence_request",
            "obligation": "obligation_review",
            "task": "general",
        }.get(entity_type, "general")

    @staticmethod
    def _linked_entity_type_for_entity(entity_type: str) -> str:
        return entity_type if entity_type in {"risk", "control", "evidence", "obligation", "task"} else "general"

    def _create_task_for_match(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        entity: dict,
        rule: AutomationRule,
        action_config: dict,
        dry_run: bool,
    ) -> Task | None:
        if dry_run:
            return None

        priority = str(action_config.get("priority") or rule.priority or "normal")
        prefix = str(action_config.get("task_title_prefix") or "Automation")
        task = Task(
            organization_id=organization_id,
            title=f"{prefix}: {entity['title']}",
            description=str(action_config.get("task_description") or f"Generated by automation rule {rule.name}"),
            status="open",
            priority=priority,
            task_type=self._task_type_for_entity(str(entity["entity_type"])),
            owner_user_id=entity.get("owner_user_id"),
            created_by_user_id=actor_user_id,
            due_date=None,
            linked_entity_type=self._linked_entity_type_for_entity(str(entity["entity_type"])),
            linked_entity_id=entity["entity_id"],
            source="system_generated",
            reminder_status="none",
            metadata_json={"automation_rule_id": str(rule.id), "condition_type": rule.condition_type},
        )
        self.db.add(task)
        self.db.flush()
        return task

    def _queue_email_for_match(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        entity: dict,
        task_title: str,
        dry_run: bool,
    ) -> uuid.UUID | None:
        owner_user_id = entity.get("owner_user_id")
        if owner_user_id is None:
            return None

        user = self.db.execute(select(User).where(User.id == owner_user_id)).scalar_one_or_none()
        if user is None or not user.email:
            return None

        if dry_run:
            return uuid.uuid4()

        SeedService.ensure_global_email_templates(self.db)
        outbox_id = TaskService(self.db).queue_task_notification(
            organization_id=organization_id,
            created_by_user_id=actor_user_id,
            owner_user=user,
            task_title=task_title,
            template_key="task_assigned",
            event_type="automation.reminder",
        )
        return outbox_id

    def run_rule(
        self,
        *,
        rule: AutomationRule,
        actor_user_id: uuid.UUID,
        trigger_source: str,
        dry_run: bool,
        scheduled_run_at: datetime | None = None,
        allow_scheduled_placeholder: bool = False,
    ) -> AutomationRuleExecution:
        if rule.status != "active":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rule is not active")
        if not allow_scheduled_placeholder and rule.trigger_type != "manual_scan":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only manual_scan rules can run in this endpoint")

        self.validate_rule_types(rule.condition_type, rule.action_type)

        started = self.now()
        execution = AutomationRuleExecution(
            organization_id=rule.organization_id,
            rule_id=rule.id,
            status="running",
            started_at=started,
            matched_count=0,
            action_count=0,
            skipped_count=0,
            error_count=0,
            idempotency_key=f"automation-exec:{rule.organization_id}:{rule.id}:{started.isoformat()}",
            trigger_source=trigger_source,
            dry_run=dry_run,
            rule_version=rule.version,
            scheduled_run_at=scheduled_run_at,
            idempotency_scope="dry_run" if dry_run else "live",
            summary_json=None,
            created_by_user_id=actor_user_id,
        )
        self.db.add(execution)
        self.db.flush()

        matches = self.match_entities(rule.organization_id, rule.condition_type)
        execution.matched_count = len(matches)

        action_config = rule.action_config_json or {}
        created = 0
        skipped = 0
        errors = 0

        for entity in matches:
            idem = self.build_idempotency_key(
                organization_id=rule.organization_id,
                rule_id=rule.id,
                rule_version=rule.version,
                condition_type=rule.condition_type,
                action_type=rule.action_type,
                entity_type=str(entity["entity_type"]),
                entity_id=entity["entity_id"],
            )

            if not dry_run and self._existing_created_action(rule.organization_id, idem) is not None:
                self._log_action(
                    organization_id=rule.organization_id,
                    rule_id=rule.id,
                    execution_id=execution.id,
                    entity_type=str(entity["entity_type"]),
                    entity_id=entity["entity_id"],
                    action_type=rule.action_type,
                    action_status="skipped_duplicate",
                    idempotency_key=idem,
                    skipped_reason="Duplicate idempotency key already created",
                )
                skipped += 1
                continue

            try:
                created_task_id = None
                created_email_id = None
                action_status = "would_create" if dry_run else "created"
                skipped_reason = None

                if rule.action_type == "create_task":
                    task = self._create_task_for_match(
                        organization_id=rule.organization_id,
                        actor_user_id=actor_user_id,
                        entity=entity,
                        rule=rule,
                        action_config=action_config,
                        dry_run=dry_run,
                    )
                    created_task_id = task.id if task else None

                elif rule.action_type == "queue_email_reminder":
                    email_id = self._queue_email_for_match(
                        organization_id=rule.organization_id,
                        actor_user_id=actor_user_id,
                        entity=entity,
                        task_title=str(entity["title"]),
                        dry_run=dry_run,
                    )
                    if email_id is None:
                        action_status = "skipped_invalid"
                        skipped_reason = "No valid recipient"
                    else:
                        created_email_id = email_id

                elif rule.action_type == "create_task_and_queue_email":
                    task = self._create_task_for_match(
                        organization_id=rule.organization_id,
                        actor_user_id=actor_user_id,
                        entity=entity,
                        rule=rule,
                        action_config=action_config,
                        dry_run=dry_run,
                    )
                    created_task_id = task.id if task else None
                    email_id = self._queue_email_for_match(
                        organization_id=rule.organization_id,
                        actor_user_id=actor_user_id,
                        entity=entity,
                        task_title=task.title if task else str(entity["title"]),
                        dry_run=dry_run,
                    )
                    if email_id is None:
                        action_status = "skipped_invalid"
                        skipped_reason = "Task created, email recipient not resolvable"
                    else:
                        created_email_id = email_id

                self._log_action(
                    organization_id=rule.organization_id,
                    rule_id=rule.id,
                    execution_id=execution.id,
                    entity_type=str(entity["entity_type"]),
                    entity_id=entity["entity_id"],
                    action_type=rule.action_type,
                    action_status=action_status,
                    idempotency_key=idem,
                    created_task_id=created_task_id,
                    created_email_outbox_id=created_email_id,
                    skipped_reason=skipped_reason,
                )

                if action_status in {"created", "would_create"}:
                    created += 1
                else:
                    skipped += 1

            except Exception as exc:  # per-entity error tracking
                self._log_action(
                    organization_id=rule.organization_id,
                    rule_id=rule.id,
                    execution_id=execution.id,
                    entity_type=str(entity["entity_type"]),
                    entity_id=entity["entity_id"],
                    action_type=rule.action_type,
                    action_status="failed",
                    idempotency_key=idem,
                    error_message=str(exc),
                )
                errors += 1

        execution.action_count = created
        execution.skipped_count = skipped
        execution.error_count = errors
        execution.finished_at = self.now()
        execution.status = "completed_with_errors" if errors > 0 else "completed"
        execution.summary_json = {
            "matched_count": execution.matched_count,
            "action_count": created,
            "skipped_count": skipped,
            "error_count": errors,
            "dry_run": dry_run,
        }

        rule.last_run_at = execution.finished_at
        if dry_run:
            rule.last_dry_run_at = execution.finished_at
        if trigger_source == "scheduled_due_run":
            rule.last_scheduled_run_at = execution.finished_at
            if rule.schedule_cadence:
                rule.next_run_at = self.calculate_next_run_at(cadence=rule.schedule_cadence, base_time=execution.finished_at)

        self.db.flush()
        return execution

    def run_due_scheduled_rules(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        dry_run: bool,
        limit: int,
    ) -> list[AutomationRuleExecution]:
        rules = self.due_scheduled_rules(organization_id, limit=limit)
        executions: list[AutomationRuleExecution] = []
        now = self.now()
        for rule in rules:
            effective_dry_run = bool(dry_run or rule.run_mode == "dry_run")
            execution = self.run_rule(
                rule=rule,
                actor_user_id=actor_user_id,
                trigger_source="scheduled_due_run",
                dry_run=effective_dry_run,
                scheduled_run_at=now,
                allow_scheduled_placeholder=True,
            )
            executions.append(execution)
        return executions

    def summary(self, organization_id: uuid.UUID) -> dict[str, int | float | list[str]]:
        since = self.now() - timedelta(hours=24)

        active_rules = int(self.db.execute(select(func.count(AutomationRule.id)).where(AutomationRule.organization_id == organization_id, AutomationRule.status == "active")).scalar_one())
        inactive_rules = int(self.db.execute(select(func.count(AutomationRule.id)).where(AutomationRule.organization_id == organization_id, AutomationRule.status == "inactive")).scalar_one())
        archived_rules = int(self.db.execute(select(func.count(AutomationRule.id)).where(AutomationRule.organization_id == organization_id, AutomationRule.status == "archived")).scalar_one())

        executions_last_24h = int(self.db.execute(select(func.count(AutomationRuleExecution.id)).where(AutomationRuleExecution.organization_id == organization_id, AutomationRuleExecution.created_at >= since)).scalar_one())

        actions_created_last_24h = int(self.db.execute(select(func.count(AutomationActionLog.id)).where(AutomationActionLog.organization_id == organization_id, AutomationActionLog.created_at >= since, AutomationActionLog.action_status == "created")).scalar_one())
        duplicate_actions_skipped_last_24h = int(self.db.execute(select(func.count(AutomationActionLog.id)).where(AutomationActionLog.organization_id == organization_id, AutomationActionLog.created_at >= since, AutomationActionLog.action_status == "skipped_duplicate")).scalar_one())
        failed_actions_last_24h = int(self.db.execute(select(func.count(AutomationActionLog.id)).where(AutomationActionLog.organization_id == organization_id, AutomationActionLog.created_at >= since, AutomationActionLog.action_status == "failed")).scalar_one())
        execution_error_rate_last_24h = round((failed_actions_last_24h / actions_created_last_24h), 4) if actions_created_last_24h > 0 else 0.0
        active_rows = self.db.execute(
            select(AutomationRule).where(AutomationRule.organization_id == organization_id, AutomationRule.status == "active")
        ).scalars().all()
        stale_active_rules = int(sum(1 for row in active_rows if bool(self.rule_payload(rule=row).get("stale_rule"))))
        active_scheduled_rules_overdue = int(sum(1 for row in active_rows if bool(self.rule_payload(rule=row).get("schedule_overdue"))))
        context_flags: list[str] = []
        if executions_last_24h == 0:
            context_flags.append("no_recent_executions")
        if execution_error_rate_last_24h > 0:
            context_flags.append("action_failures_present")
        if stale_active_rules > 0:
            context_flags.append("stale_active_rules")
        if active_scheduled_rules_overdue > 0:
            context_flags.append("scheduled_rules_overdue")

        return {
            "active_rules": active_rules,
            "inactive_rules": inactive_rules,
            "archived_rules": archived_rules,
            "executions_last_24h": executions_last_24h,
            "actions_created_last_24h": actions_created_last_24h,
            "duplicate_actions_skipped_last_24h": duplicate_actions_skipped_last_24h,
            "failed_actions_last_24h": failed_actions_last_24h,
            "execution_error_rate_last_24h": execution_error_rate_last_24h,
            "stale_active_rules": stale_active_rules,
            "active_scheduled_rules_overdue": active_scheduled_rules_overdue,
            "context_flags": context_flags,
        }

    def schedule_summary(self, organization_id: uuid.UUID) -> dict:
        now = self.now()
        since = now - timedelta(hours=24)

        scheduled_rules = int(self.db.execute(select(func.count(AutomationRule.id)).where(AutomationRule.organization_id == organization_id, AutomationRule.trigger_type == "scheduled_placeholder")).scalar_one())
        enabled_schedules = int(self.db.execute(select(func.count(AutomationRule.id)).where(AutomationRule.organization_id == organization_id, AutomationRule.trigger_type == "scheduled_placeholder", AutomationRule.schedule_enabled.is_(True), AutomationRule.status == "active")).scalar_one())
        disabled_schedules = max(0, scheduled_rules - enabled_schedules)

        due_rows = self.due_scheduled_rules(organization_id, limit=1000)
        due_now = len(due_rows)

        last_scheduled_run_at = self.db.execute(
            select(func.max(AutomationRuleExecution.finished_at)).where(
                AutomationRuleExecution.organization_id == organization_id,
                AutomationRuleExecution.trigger_source == "scheduled_due_run",
            )
        ).scalar_one()

        next_due_run_at = self.db.execute(
            select(func.min(AutomationRule.next_run_at)).where(
                AutomationRule.organization_id == organization_id,
                AutomationRule.trigger_type == "scheduled_placeholder",
                AutomationRule.schedule_enabled.is_(True),
                AutomationRule.status == "active",
                AutomationRule.next_run_at.is_not(None),
            )
        ).scalar_one()

        dry_run_executions_last_24h = int(self.db.execute(select(func.count(AutomationRuleExecution.id)).where(AutomationRuleExecution.organization_id == organization_id, AutomationRuleExecution.created_at >= since, AutomationRuleExecution.dry_run.is_(True))).scalar_one())
        live_scheduled_executions_last_24h = int(self.db.execute(select(func.count(AutomationRuleExecution.id)).where(AutomationRuleExecution.organization_id == organization_id, AutomationRuleExecution.created_at >= since, AutomationRuleExecution.trigger_source == "scheduled_due_run", AutomationRuleExecution.dry_run.is_(False))).scalar_one())
        scheduled_active_rows = self.db.execute(
            select(AutomationRule).where(
                AutomationRule.organization_id == organization_id,
                AutomationRule.status == "active",
                AutomationRule.trigger_type == "scheduled_placeholder",
                AutomationRule.schedule_enabled.is_(True),
            )
        ).scalars().all()
        overdue_scheduled_rules = int(sum(1 for row in scheduled_active_rows if bool(self.rule_payload(rule=row, now=now).get("schedule_overdue"))))
        stalled_scheduled_rules = int(
            sum(
                1
                for row in scheduled_active_rows
                if (
                    self._to_utc(row.last_scheduled_run_at) is None
                    and (self._to_utc(row.created_at) or now) <= now - timedelta(hours=AUTOMATION_STALLED_SCHEDULE_HOURS)
                )
                or (
                    self._to_utc(row.last_scheduled_run_at) is not None
                    and (self._to_utc(row.last_scheduled_run_at) or now) <= now - timedelta(hours=AUTOMATION_STALLED_SCHEDULE_HOURS)
                )
            )
        )
        context_flags: list[str] = []
        if due_now > 0:
            context_flags.append("rules_due_now")
        if overdue_scheduled_rules > 0:
            context_flags.append("overdue_scheduled_rules")
        if stalled_scheduled_rules > 0:
            context_flags.append("stalled_schedules")
        if live_scheduled_executions_last_24h == 0 and enabled_schedules > 0:
            context_flags.append("no_live_scheduled_runs_24h")

        return {
            "scheduled_rules": scheduled_rules,
            "enabled_schedules": enabled_schedules,
            "due_now": due_now,
            "disabled_schedules": disabled_schedules,
            "last_scheduled_run_at": last_scheduled_run_at,
            "next_due_run_at": next_due_run_at,
            "dry_run_executions_last_24h": dry_run_executions_last_24h,
            "live_scheduled_executions_last_24h": live_scheduled_executions_last_24h,
            "overdue_scheduled_rules": overdue_scheduled_rules,
            "stalled_scheduled_rules": stalled_scheduled_rules,
            "context_flags": context_flags,
        }
