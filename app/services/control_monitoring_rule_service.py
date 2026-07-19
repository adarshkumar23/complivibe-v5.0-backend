import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.control_monitoring_definition import ControlMonitoringDefinition
from app.models.control_monitoring_result import ControlMonitoringResult
from app.models.control_monitoring_rule import ControlMonitoringRule
from app.models.control_monitoring_rule_execution import ControlMonitoringRuleExecution
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.membership import Membership
from app.models.risk import Risk
from app.models.risk_control_link import RiskControlLink
from app.models.task import Task
from app.models.user import User
from app.services.seed_service import SeedService
from app.services.task_service import TaskService

RULE_CONDITION_ALLOWLIST: dict[str, set[str]] = {
    "overdue_check": {"days_overdue_threshold"},
    "consecutive_fails": {"fail_count"},
    "evidence_gap": {"days_without_evidence"},
    "task_overdue": {"days_overdue_threshold"},
    "risk_threshold_breach": {"risk_levels"},
}
RISK_LEVELS = {"critical", "high", "medium", "low"}


class ControlMonitoringRuleService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def as_utc(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)

    def require_rule_in_org(self, organization_id: uuid.UUID, rule_id: uuid.UUID) -> ControlMonitoringRule:
        row = self.db.execute(
            select(ControlMonitoringRule).where(
                ControlMonitoringRule.id == rule_id,
                ControlMonitoringRule.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control monitoring rule not found")
        return row

    def require_execution_in_org(self, organization_id: uuid.UUID, execution_id: uuid.UUID) -> ControlMonitoringRuleExecution:
        row = self.db.execute(
            select(ControlMonitoringRuleExecution).where(
                ControlMonitoringRuleExecution.id == execution_id,
                ControlMonitoringRuleExecution.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control monitoring rule execution not found")
        return row

    def validate_scope_definition_ids(self, organization_id: uuid.UUID, scope_definition_ids: list[uuid.UUID] | None) -> list[uuid.UUID] | None:
        if not scope_definition_ids:
            return None
        existing = set(
            self.db.execute(
                select(ControlMonitoringDefinition.id).where(
                    ControlMonitoringDefinition.organization_id == organization_id,
                    ControlMonitoringDefinition.id.in_(scope_definition_ids),
                )
            ).scalars().all()
        )
        missing = [definition_id for definition_id in scope_definition_ids if definition_id not in existing]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="scope_definition_ids must all belong to the organization",
            )
        return scope_definition_ids

    def validate_condition_json(self, rule_type: str, condition_json: dict) -> dict:
        allowed_keys = RULE_CONDITION_ALLOWLIST.get(rule_type)
        if allowed_keys is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported rule_type")

        unknown = sorted([key for key in condition_json.keys() if key not in allowed_keys])
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"condition_json has unsupported keys for {rule_type}: {', '.join(unknown)}",
            )

        if rule_type in {"overdue_check", "task_overdue"}:
            value = condition_json.get("days_overdue_threshold")
            if not isinstance(value, int) or value < 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="days_overdue_threshold must be an integer >= 0")
        elif rule_type == "consecutive_fails":
            value = condition_json.get("fail_count")
            if not isinstance(value, int) or value < 2 or value > 10:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="fail_count must be an integer between 2 and 10")
        elif rule_type == "evidence_gap":
            value = condition_json.get("days_without_evidence")
            if not isinstance(value, int) or value < 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="days_without_evidence must be an integer >= 0")
        elif rule_type == "risk_threshold_breach":
            levels = condition_json.get("risk_levels")
            if not isinstance(levels, list) or len(levels) == 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="risk_levels must be a non-empty list")
            invalid = sorted([level for level in levels if level not in RISK_LEVELS])
            if invalid:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="risk_levels contains unsupported values")

        required = allowed_keys
        missing = [key for key in required if key not in condition_json]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"condition_json missing required keys for {rule_type}: {', '.join(missing)}",
            )

        return condition_json

    def _scoped_definitions(self, organization_id: uuid.UUID, rule: ControlMonitoringRule) -> list[ControlMonitoringDefinition]:
        stmt = select(ControlMonitoringDefinition).where(
            ControlMonitoringDefinition.organization_id == organization_id,
            ControlMonitoringDefinition.status == "active",
        )
        if rule.scope_definition_ids:
            scope_ids = [uuid.UUID(str(v)) for v in rule.scope_definition_ids]
            stmt = stmt.where(ControlMonitoringDefinition.id.in_(scope_ids))
        return self.db.execute(stmt.order_by(ControlMonitoringDefinition.created_at.asc())).scalars().all()

    def _consecutive_fail_count(self, organization_id: uuid.UUID, definition_id: uuid.UUID) -> int:
        rows = self.db.execute(
            select(ControlMonitoringResult.check_status)
            .where(
                ControlMonitoringResult.organization_id == organization_id,
                ControlMonitoringResult.definition_id == definition_id,
            )
            .order_by(ControlMonitoringResult.checked_at.desc(), ControlMonitoringResult.id.desc())
            .limit(20)
        ).scalars().all()
        count = 0
        for status_value in rows:
            if status_value == "fail":
                count += 1
            else:
                break
        return count

    def _definition_matches(self, organization_id: uuid.UUID, rule: ControlMonitoringRule) -> list[dict]:
        now = self.utcnow()
        matches: list[dict] = []
        definitions = self._scoped_definitions(organization_id, rule)

        if rule.rule_type == "overdue_check":
            threshold = int(rule.condition_json["days_overdue_threshold"])
            cutoff = now - timedelta(days=threshold)
            for definition in definitions:
                next_due = self.as_utc(definition.next_check_due_at)
                if next_due is not None and next_due <= cutoff:
                    matches.append({"definition": definition, "reason": "overdue_check"})

        elif rule.rule_type == "consecutive_fails":
            threshold = int(rule.condition_json["fail_count"])
            for definition in definitions:
                count = self._consecutive_fail_count(organization_id, definition.id)
                if count >= threshold:
                    matches.append({"definition": definition, "reason": "consecutive_fails", "consecutive_fails": count})

        elif rule.rule_type == "evidence_gap":
            threshold = int(rule.condition_json["days_without_evidence"])
            cutoff = now - timedelta(days=threshold)
            control_ids = [d.control_id for d in definitions]
            # One grouped query for every scoped definition's control instead of one query per
            # definition -- an org can have thousands of active monitoring definitions in scope.
            last_collected_by_control: dict[uuid.UUID, datetime | None] = {}
            if control_ids:
                rows = self.db.execute(
                    select(EvidenceControlLink.control_id, func.max(EvidenceItem.collected_at))
                    .select_from(EvidenceControlLink)
                    .join(
                        EvidenceItem,
                        and_(
                            EvidenceItem.id == EvidenceControlLink.evidence_item_id,
                            EvidenceItem.organization_id == organization_id,
                        ),
                    )
                    .where(
                        EvidenceControlLink.organization_id == organization_id,
                        EvidenceControlLink.control_id.in_(control_ids),
                        EvidenceControlLink.link_status == "active",
                    )
                    .group_by(EvidenceControlLink.control_id)
                ).all()
                last_collected_by_control = {control_id: collected_at for control_id, collected_at in rows}

            for definition in definitions:
                last_collected_at = self.as_utc(last_collected_by_control.get(definition.control_id))
                if last_collected_at is None or last_collected_at <= cutoff:
                    matches.append({"definition": definition, "reason": "evidence_gap"})

        elif rule.rule_type == "task_overdue":
            threshold = int(rule.condition_json["days_overdue_threshold"])
            cutoff = now - timedelta(days=threshold)
            definition_ids = [d.id for d in definitions]
            overdue_by_definition: dict[uuid.UUID, int] = {}
            if definition_ids:
                rows = self.db.execute(
                    select(Task.linked_entity_id, func.count(Task.id))
                    .where(
                        Task.organization_id == organization_id,
                        Task.linked_entity_type == "control_monitoring_definition",
                        Task.linked_entity_id.in_(definition_ids),
                        Task.status.in_(["open", "in_progress", "blocked"]),
                        Task.due_date.is_not(None),
                        Task.due_date <= cutoff,
                    )
                    .group_by(Task.linked_entity_id)
                ).all()
                overdue_by_definition = {definition_id: int(count) for definition_id, count in rows}

            for definition in definitions:
                overdue_tasks = overdue_by_definition.get(definition.id, 0)
                if overdue_tasks > 0:
                    matches.append({"definition": definition, "reason": "task_overdue", "overdue_tasks": overdue_tasks})

        elif rule.rule_type == "risk_threshold_breach":
            levels = set(rule.condition_json["risk_levels"])
            control_ids = [d.control_id for d in definitions]
            breach_by_control: dict[uuid.UUID, int] = {}
            if control_ids:
                rows = self.db.execute(
                    select(RiskControlLink.control_id, func.count(Risk.id))
                    .select_from(RiskControlLink)
                    .join(
                        Risk,
                        and_(
                            Risk.id == RiskControlLink.risk_id,
                            Risk.organization_id == organization_id,
                        ),
                    )
                    .where(
                        RiskControlLink.organization_id == organization_id,
                        RiskControlLink.control_id.in_(control_ids),
                        RiskControlLink.status == "active",
                        Risk.severity.in_(levels),
                    )
                    .group_by(RiskControlLink.control_id)
                ).all()
                breach_by_control = {control_id: int(count) for control_id, count in rows}

            for definition in definitions:
                breach_count = breach_by_control.get(definition.control_id, 0)
                if breach_count > 0:
                    matches.append({"definition": definition, "reason": "risk_threshold_breach", "breach_count": breach_count})

        return matches

    def _existing_action_keys_for_today(self, organization_id: uuid.UUID, rule_id: uuid.UUID, now: datetime) -> set[str]:
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        rows = self.db.execute(
            select(ControlMonitoringRuleExecution.execution_summary_json).where(
                ControlMonitoringRuleExecution.organization_id == organization_id,
                ControlMonitoringRuleExecution.rule_id == rule_id,
                ControlMonitoringRuleExecution.dry_run.is_(False),
                ControlMonitoringRuleExecution.triggered_at >= day_start,
                ControlMonitoringRuleExecution.triggered_at < day_end,
            )
        ).scalars().all()

        action_keys: set[str] = set()
        for summary in rows:
            if isinstance(summary, dict):
                keys = summary.get("action_keys", [])
                if isinstance(keys, list):
                    action_keys.update(str(v) for v in keys)
        return action_keys

    def _ensure_member_user(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> User | None:
        membership = self.db.execute(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.user_id == user_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if membership is None:
            return None
        user = self.db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if user is None or not user.is_active or user.status != "active":
            return None
        return user

    def evaluate_rule(
        self,
        *,
        organization_id: uuid.UUID,
        rule: ControlMonitoringRule,
        # None when scheduler-driven; the columns it feeds are nullable.
        actor_user_id: uuid.UUID | None,
        dry_run: bool,
    ) -> ControlMonitoringRuleExecution:
        now = self.utcnow()
        matches = self._definition_matches(organization_id, rule)

        existing_keys = self._existing_action_keys_for_today(organization_id, rule.id, now)
        created_alert_ids: list[str] = []
        created_task_ids: list[str] = []
        queued_outbox_ids: list[str] = []
        action_keys: list[str] = []
        skipped_duplicates: list[str] = []

        created_or_seen_in_run: set[str] = set()
        task_service = TaskService(self.db)

        for match in matches:
            definition: ControlMonitoringDefinition = match["definition"]
            action_key = f"{rule.id}:{rule.action_type}:{definition.id}:{now.date().isoformat()}"
            if action_key in existing_keys or action_key in created_or_seen_in_run:
                skipped_duplicates.append(action_key)
                continue

            if dry_run:
                action_keys.append(action_key)
                created_or_seen_in_run.add(action_key)
                continue

            owner_user = self._ensure_member_user(organization_id, definition.owner_user_id)
            if owner_user is None:
                skipped_duplicates.append(action_key)
                continue

            action_config = rule.action_config_json if isinstance(rule.action_config_json, dict) else {}
            if rule.action_type == "queue_reminder":
                SeedService.ensure_global_email_templates(self.db)
                outbox_id = task_service.queue_task_notification(
                    organization_id=organization_id,
                    created_by_user_id=actor_user_id,
                    owner_user=owner_user,
                    task_title=str(action_config.get("task_title") or f"Monitoring reminder: {definition.name}"),
                    template_key=str(action_config.get("template_key") or "task_assigned"),
                    event_type="control_monitoring.rule_reminder",
                )
                queued_outbox_ids.append(str(outbox_id))
            elif rule.action_type == "create_alert":
                alert = ControlMonitoringAlert(
                    organization_id=organization_id,
                    rule_id=rule.id,
                    definition_id=definition.id,
                    control_id=definition.control_id,
                    alert_type="rule_generated",
                    severity=str(action_config.get("severity") or "medium"),
                    status="open",
                    title=str(action_config.get("title") or f"Monitoring Alert: {definition.name}"),
                    description=str(action_config.get("description") or f"Rule {rule.name} matched {definition.name}"),
                    alert_context_json={
                        "source": "control_monitoring_rule",
                        "rule_id": str(rule.id),
                        "rule_type": rule.rule_type,
                        "match_reason": match.get("reason"),
                    },
                    assigned_to_user_id=owner_user.id,
                )
                self.db.add(alert)
                self.db.flush()
                created_alert_ids.append(str(alert.id))

                from app.compliance.services.webhook_service import WebhookService

                WebhookService(self.db).emit(
                    organization_id,
                    "alert.triggered",
                    {
                        "alert_id": str(alert.id),
                        "title": alert.title,
                        "severity": alert.severity,
                        "rule_id": str(rule.id),
                        "control_id": str(definition.control_id) if definition.control_id else None,
                    },
                )
            else:
                task = Task(
                    organization_id=organization_id,
                    title=str(action_config.get("title") or f"Monitoring Task: {definition.name}"),
                    description=str(action_config.get("description") or f"Rule {rule.name} matched {definition.name}"),
                    status="open",
                    priority=str(action_config.get("priority") or "normal"),
                    task_type=str(action_config.get("task_type") or "general"),
                    owner_user_id=owner_user.id,
                    created_by_user_id=actor_user_id,
                    due_date=None,
                    linked_entity_type="control_monitoring_definition",
                    linked_entity_id=definition.id,
                    source="automation",
                    reminder_status="none",
                    metadata_json={
                        "source": "control_monitoring_rule",
                        "rule_id": str(rule.id),
                        "rule_type": rule.rule_type,
                        "match_reason": match.get("reason"),
                    },
                )
                self.db.add(task)
                self.db.flush()
                created_task_ids.append(str(task.id))

            action_keys.append(action_key)
            created_or_seen_in_run.add(action_key)

        matched_count = len(matches)
        action_count = len(action_keys)
        skipped_count = len(skipped_duplicates)

        execution = ControlMonitoringRuleExecution(
            organization_id=organization_id,
            rule_id=rule.id,
            triggered_at=now,
            dry_run=dry_run,
            matched_count=matched_count,
            action_count=action_count,
            skipped_count=skipped_count,
            execution_summary_json={
                "rule_id": str(rule.id),
                "rule_name": rule.name,
                "rule_type": rule.rule_type,
                "action_type": rule.action_type,
                "dry_run": dry_run,
                "would_match": matched_count,
                "would_act": action_count,
                "matched_definition_ids": [str(m["definition"].id) for m in matches],
                "action_keys": action_keys,
                "created_alert_ids": created_alert_ids,
                "created_task_ids": created_task_ids,
                "queued_outbox_ids": queued_outbox_ids,
                "skipped_duplicates": skipped_duplicates,
            },
        )
        self.db.add(execution)
        rule.last_evaluated_at = now
        self.db.flush()
        return execution

    def summary(self, organization_id: uuid.UUID) -> dict[str, int | dict[str, int]]:
        total_rules = int(
            self.db.execute(select(func.count(ControlMonitoringRule.id)).where(ControlMonitoringRule.organization_id == organization_id)).scalar_one()
        )
        active_rules = int(
            self.db.execute(
                select(func.count(ControlMonitoringRule.id)).where(
                    ControlMonitoringRule.organization_id == organization_id,
                    ControlMonitoringRule.status == "active",
                )
            ).scalar_one()
        )
        inactive_rules = int(
            self.db.execute(
                select(func.count(ControlMonitoringRule.id)).where(
                    ControlMonitoringRule.organization_id == organization_id,
                    ControlMonitoringRule.status == "inactive",
                )
            ).scalar_one()
        )
        archived_rules = int(
            self.db.execute(
                select(func.count(ControlMonitoringRule.id)).where(
                    ControlMonitoringRule.organization_id == organization_id,
                    ControlMonitoringRule.status == "archived",
                )
            ).scalar_one()
        )

        execution_base = [ControlMonitoringRuleExecution.organization_id == organization_id]
        total_executions = int(self.db.execute(select(func.count(ControlMonitoringRuleExecution.id)).where(*execution_base)).scalar_one())
        total_dry_runs = int(
            self.db.execute(select(func.count(ControlMonitoringRuleExecution.id)).where(*execution_base, ControlMonitoringRuleExecution.dry_run.is_(True))).scalar_one()
        )
        total_live_runs = int(
            self.db.execute(select(func.count(ControlMonitoringRuleExecution.id)).where(*execution_base, ControlMonitoringRuleExecution.dry_run.is_(False))).scalar_one()
        )
        total_matched = int(self.db.execute(select(func.coalesce(func.sum(ControlMonitoringRuleExecution.matched_count), 0)).where(*execution_base)).scalar_one())
        total_actions = int(self.db.execute(select(func.coalesce(func.sum(ControlMonitoringRuleExecution.action_count), 0)).where(*execution_base)).scalar_one())
        total_skipped = int(self.db.execute(select(func.coalesce(func.sum(ControlMonitoringRuleExecution.skipped_count), 0)).where(*execution_base)).scalar_one())

        by_rule_type_rows = self.db.execute(
            select(ControlMonitoringRule.rule_type, func.count(ControlMonitoringRule.id))
            .where(ControlMonitoringRule.organization_id == organization_id)
            .group_by(ControlMonitoringRule.rule_type)
        ).all()
        by_action_type_rows = self.db.execute(
            select(ControlMonitoringRule.action_type, func.count(ControlMonitoringRule.id))
            .where(ControlMonitoringRule.organization_id == organization_id)
            .group_by(ControlMonitoringRule.action_type)
        ).all()

        return {
            "total_rules": total_rules,
            "active_rules": active_rules,
            "inactive_rules": inactive_rules,
            "archived_rules": archived_rules,
            "total_executions": total_executions,
            "total_dry_runs": total_dry_runs,
            "total_live_runs": total_live_runs,
            "total_matched": total_matched,
            "total_actions": total_actions,
            "total_skipped": total_skipped,
            "by_rule_type": {str(key): int(value) for key, value in by_rule_type_rows},
            "by_action_type": {str(key): int(value) for key, value in by_action_type_rows},
        }
