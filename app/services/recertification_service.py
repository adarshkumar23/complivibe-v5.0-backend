import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.control import Control
from app.models.control_test_definition import ControlTestDefinition
from app.models.control_test_run import ControlTestRun
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.evidence_recertification_policy import EvidenceRecertificationPolicy
from app.models.membership import Membership
from app.models.recertification_action_log import RecertificationActionLog
from app.models.recertification_run import RecertificationRun
from app.models.task import Task
from app.models.user import User
from app.services.seed_service import SeedService
from app.services.task_service import TaskService
from app.core.validation import validate_choice

ALLOWED_SCOPE_TYPES = {"all_evidence", "evidence_type", "evidence_item", "control"}
ALLOWED_CADENCE = {"monthly", "quarterly", "semi_annual", "annual"}
ALLOWED_RUN_TYPES = {"evidence_recertification", "control_reassessment", "combined"}


class RecertificationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)

    @classmethod
    def _to_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def validate_scope_type(scope_type: str) -> None:
        scope_type = validate_choice(scope_type, ALLOWED_SCOPE_TYPES, "scope_type", status_code=status.HTTP_400_BAD_REQUEST)
    @staticmethod
    def validate_cadence(cadence: str) -> None:
        cadence = validate_choice(cadence, ALLOWED_CADENCE, "cadence", status_code=status.HTTP_400_BAD_REQUEST)
    def ensure_owner_is_active_member(self, organization_id: uuid.UUID, owner_user_id: uuid.UUID | None) -> None:
        if owner_user_id is None:
            return
        membership = self.db.execute(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.user_id == owner_user_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="owner_user_id must be an active member of the organization",
            )

    def calculate_next_run_at(self, cadence: str, *, base_time: datetime | None = None) -> datetime:
        base = self._to_utc(base_time) or self.now()
        if cadence == "monthly":
            return base + timedelta(days=30)
        if cadence == "quarterly":
            return base + timedelta(days=90)
        if cadence == "semi_annual":
            return base + timedelta(days=182)
        return base + timedelta(days=365)

    def _policy_scope_condition(self, policy: EvidenceRecertificationPolicy):
        scope = policy.scope_config_json or {}
        if policy.scope_type == "all_evidence":
            return True
        if policy.scope_type == "evidence_type":
            evidence_type = scope.get("evidence_type")
            if not evidence_type:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scope_config_json.evidence_type is required")
            return EvidenceItem.evidence_type == str(evidence_type)
        if policy.scope_type == "evidence_item":
            evidence_id = scope.get("evidence_item_id")
            if not evidence_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scope_config_json.evidence_item_id is required")
            return EvidenceItem.id == uuid.UUID(str(evidence_id))
        if policy.scope_type == "control":
            control_id = scope.get("control_id")
            if not control_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scope_config_json.control_id is required")
            return EvidenceItem.id.in_(
                select(EvidenceControlLink.evidence_item_id).where(
                    EvidenceControlLink.organization_id == policy.organization_id,
                    EvidenceControlLink.control_id == uuid.UUID(str(control_id)),
                    EvidenceControlLink.link_status == "active",
                )
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported scope_type")

    def _due_evidence_query(self, organization_id: uuid.UUID, lead_time_days: int):
        now = self.now()
        due_before = now + timedelta(days=lead_time_days)
        return (
            select(EvidenceItem)
            .where(
                EvidenceItem.organization_id == organization_id,
                EvidenceItem.status == "active",
                or_(
                    EvidenceItem.freshness_status == "expired",
                    and_(
                        EvidenceItem.valid_until.is_not(None),
                        EvidenceItem.valid_until <= due_before,
                    ),
                    EvidenceItem.review_status.in_(["not_reviewed", "needs_review"]),
                ),
            )
            .order_by(EvidenceItem.valid_until.asc().nulls_last(), EvidenceItem.created_at.desc())
        )

    def discover_due_evidence(
        self,
        *,
        organization_id: uuid.UUID,
        policy: EvidenceRecertificationPolicy | None,
        lead_time_days: int,
        limit: int,
    ) -> list[dict]:
        stmt = self._due_evidence_query(organization_id, lead_time_days)
        if policy is not None:
            condition = self._policy_scope_condition(policy)
            if condition is not True:
                stmt = stmt.where(condition)

        items = list(self.db.execute(stmt.limit(limit)).scalars().all())
        out: list[dict] = []
        for evidence in items:
            links = self.db.execute(
                select(EvidenceControlLink, Control)
                .join(Control, Control.id == EvidenceControlLink.control_id)
                .where(
                    EvidenceControlLink.organization_id == organization_id,
                    EvidenceControlLink.evidence_item_id == evidence.id,
                    EvidenceControlLink.link_status == "active",
                    Control.organization_id == organization_id,
                )
            ).all()

            linked_controls = [
                {
                    "control_id": control.id,
                    "title": control.title,
                    "status": control.status,
                }
                for _, control in links
            ]

            due_reason = "needs_review"
            priority = "normal"
            if evidence.freshness_status == "expired":
                due_reason = "expired"
                priority = "high"
            elif evidence.valid_until and self._to_utc(evidence.valid_until) and self._to_utc(evidence.valid_until) <= self.now() + timedelta(days=lead_time_days):
                due_reason = "expiring_soon"

            out.append(
                {
                    "evidence_id": evidence.id,
                    "title": evidence.title,
                    "review_status": evidence.review_status,
                    "freshness_status": evidence.freshness_status,
                    "valid_until": evidence.valid_until,
                    "due_reason": due_reason,
                    "priority": priority,
                    "owner_user_id": evidence.uploaded_by_user_id,
                    "linked_controls": linked_controls,
                }
            )
        return out

    def discover_due_control_tests(
        self,
        *,
        organization_id: uuid.UUID,
        due_within_days: int,
        limit: int,
    ) -> list[dict]:
        now = self.now()
        due_before = now + timedelta(days=due_within_days)
        rows = self.db.execute(
            select(ControlTestDefinition, Control)
            .join(Control, Control.id == ControlTestDefinition.control_id)
            .where(
                ControlTestDefinition.organization_id == organization_id,
                ControlTestDefinition.status == "active",
                ControlTestDefinition.next_due_at.is_not(None),
                ControlTestDefinition.next_due_at <= due_before,
                Control.organization_id == organization_id,
                Control.status != "archived",
            )
            .order_by(ControlTestDefinition.next_due_at.asc())
            .limit(limit)
        ).all()

        out: list[dict] = []
        for test_def, control in rows:
            latest = self.db.execute(
                select(ControlTestRun)
                .where(
                    ControlTestRun.organization_id == organization_id,
                    ControlTestRun.control_test_definition_id == test_def.id,
                )
                .order_by(ControlTestRun.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()

            due_status = "due_soon"
            next_due_at = self._to_utc(test_def.next_due_at)
            if next_due_at and next_due_at < now:
                due_status = "overdue"

            out.append(
                {
                    "test_id": test_def.id,
                    "control_id": control.id,
                    "control_title": control.title,
                    "test_name": test_def.name,
                    "next_due_at": test_def.next_due_at,
                    "due_status": due_status,
                    "latest_result": latest.result if latest else None,
                    "owner_user_id": test_def.owner_user_id or control.owner_user_id,
                }
            )
        return out

    def _existing_created_action(self, organization_id: uuid.UUID, idempotency_key: str) -> RecertificationActionLog | None:
        return self.db.execute(
            select(RecertificationActionLog).where(
                RecertificationActionLog.organization_id == organization_id,
                RecertificationActionLog.idempotency_key == idempotency_key,
                RecertificationActionLog.action_status == "created",
            )
        ).scalar_one_or_none()

    def _create_run(
        self,
        *,
        organization_id: uuid.UUID,
        policy_id: uuid.UUID | None,
        run_type: str,
        dry_run: bool,
        created_by_user_id: uuid.UUID,
    ) -> RecertificationRun:
        run_type = validate_choice(run_type, ALLOWED_RUN_TYPES, "run_type", status_code=status.HTTP_400_BAD_REQUEST)
        run = RecertificationRun(
            organization_id=organization_id,
            policy_id=policy_id,
            run_type=run_type,
            dry_run=dry_run,
            status="running",
            started_at=self.now(),
            due_count=0,
            overdue_count=0,
            task_count=0,
            email_count=0,
            skipped_duplicate_count=0,
            error_count=0,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(run)
        self.db.flush()
        return run

    def _log_action(
        self,
        *,
        organization_id: uuid.UUID,
        run_id: uuid.UUID,
        policy_id: uuid.UUID | None,
        entity_type: str,
        entity_id: uuid.UUID,
        action_type: str,
        action_status: str,
        idempotency_key: str,
        created_task_id: uuid.UUID | None = None,
        created_email_outbox_id: uuid.UUID | None = None,
        skipped_reason: str | None = None,
        error_message: str | None = None,
    ) -> RecertificationActionLog:
        row = RecertificationActionLog(
            organization_id=organization_id,
            run_id=run_id,
            policy_id=policy_id,
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

    def _build_evidence_idempotency_key(
        self,
        *,
        organization_id: uuid.UUID,
        evidence_id: uuid.UUID,
        policy_id: uuid.UUID | None,
        due_marker: str,
    ) -> str:
        marker = policy_id if policy_id is not None else "default"
        return f"recertification:{organization_id}:evidence:{evidence_id}:{marker}:{due_marker}"

    def _build_control_idempotency_key(
        self,
        *,
        organization_id: uuid.UUID,
        test_id: uuid.UUID,
        due_marker: str,
    ) -> str:
        return f"reassessment:{organization_id}:control_test:{test_id}:{due_marker}"

    def _queue_owner_email(
        self,
        *,
        organization_id: uuid.UUID,
        created_by_user_id: uuid.UUID,
        owner_user_id: uuid.UUID | None,
        task_title: str,
    ) -> uuid.UUID | None:
        if owner_user_id is None:
            return None
        owner = self.db.execute(select(User).where(User.id == owner_user_id)).scalar_one_or_none()
        if owner is None or not owner.email:
            return None
        SeedService.ensure_global_email_templates(self.db)
        return TaskService(self.db).queue_task_notification(
            organization_id=organization_id,
            created_by_user_id=created_by_user_id,
            owner_user=owner,
            task_title=task_title,
            template_key="task_assigned",
            event_type="recertification.reminder",
        )

    def run_evidence_recertification(
        self,
        *,
        organization_id: uuid.UUID,
        policy: EvidenceRecertificationPolicy | None,
        dry_run: bool,
        notify_owner: bool,
        limit: int,
        created_by_user_id: uuid.UUID,
    ) -> RecertificationRun:
        lead_time_days = policy.lead_time_days if policy else 14
        due_items = self.discover_due_evidence(
            organization_id=organization_id,
            policy=policy,
            lead_time_days=lead_time_days,
            limit=limit,
        )

        run = self._create_run(
            organization_id=organization_id,
            policy_id=policy.id if policy else None,
            run_type="evidence_recertification",
            dry_run=dry_run,
            created_by_user_id=created_by_user_id,
        )

        run.due_count = len(due_items)
        run.overdue_count = sum(1 for item in due_items if item["due_reason"] == "expired")

        created = 0
        skipped = 0
        emails = 0
        errors = 0

        for item in due_items:
            evidence_id = item["evidence_id"]
            due_marker = item["valid_until"].isoformat() if item["valid_until"] else item["due_reason"]
            idem = self._build_evidence_idempotency_key(
                organization_id=organization_id,
                evidence_id=evidence_id,
                policy_id=policy.id if policy else None,
                due_marker=due_marker,
            )
            log_idem = f"{idem}:dryrun" if dry_run else idem

            if not dry_run and self._existing_created_action(organization_id, idem) is not None:
                self._log_action(
                    organization_id=organization_id,
                    run_id=run.id,
                    policy_id=policy.id if policy else None,
                    entity_type="evidence",
                    entity_id=evidence_id,
                    action_type="create_recertification_task",
                    action_status="skipped_duplicate",
                    idempotency_key=f"{idem}:skip:{run.id}",
                    skipped_reason="Duplicate idempotency key already created",
                )
                skipped += 1
                continue

            try:
                task = None
                outbox_id = None
                if not dry_run:
                    task = Task(
                        organization_id=organization_id,
                        title=f"Review evidence: {item['title']}",
                        description=f"Recertification required ({item['due_reason']}).",
                        status="open",
                        priority=item["priority"],
                        task_type="evidence_request",
                        owner_user_id=item["owner_user_id"],
                        created_by_user_id=created_by_user_id,
                        linked_entity_type="evidence",
                        linked_entity_id=evidence_id,
                        source="evidence_workflow",
                        reminder_status="none",
                        metadata_json={"run_id": str(run.id), "due_reason": item["due_reason"]},
                    )
                    self.db.add(task)
                    self.db.flush()

                    if notify_owner:
                        outbox_id = self._queue_owner_email(
                            organization_id=organization_id,
                            created_by_user_id=created_by_user_id,
                            owner_user_id=item["owner_user_id"],
                            task_title=task.title,
                        )

                self._log_action(
                    organization_id=organization_id,
                    run_id=run.id,
                    policy_id=policy.id if policy else None,
                    entity_type="evidence",
                    entity_id=evidence_id,
                    action_type="create_recertification_task",
                    action_status="would_create" if dry_run else "created",
                    idempotency_key=log_idem,
                    created_task_id=task.id if task else None,
                    created_email_outbox_id=outbox_id,
                    skipped_reason=("No valid recipient" if notify_owner and outbox_id is None and item["owner_user_id"] else None),
                )
                if notify_owner and outbox_id:
                    emails += 1
                created += 1
            except Exception as exc:
                self._log_action(
                    organization_id=organization_id,
                    run_id=run.id,
                    policy_id=policy.id if policy else None,
                    entity_type="evidence",
                    entity_id=evidence_id,
                    action_type="create_recertification_task",
                    action_status="failed",
                    idempotency_key=(f"{idem}:error:{run.id}" if not dry_run else log_idem),
                    error_message=str(exc),
                )
                errors += 1

        run.task_count = created
        run.email_count = emails
        run.skipped_duplicate_count = skipped
        run.error_count = errors
        run.finished_at = self.now()
        run.status = "completed_with_errors" if errors else "completed"
        run.summary_json = {
            "due_count": run.due_count,
            "overdue_count": run.overdue_count,
            "task_count": run.task_count,
            "email_count": run.email_count,
            "skipped_duplicate_count": run.skipped_duplicate_count,
            "error_count": run.error_count,
            "dry_run": dry_run,
        }

        if policy is not None:
            policy.last_run_at = run.finished_at
            policy.next_run_at = self.calculate_next_run_at(policy.cadence, base_time=run.finished_at)

        self.db.flush()
        return run

    def run_control_reassessment(
        self,
        *,
        organization_id: uuid.UUID,
        dry_run: bool,
        notify_owner: bool,
        due_within_days: int,
        limit: int,
        created_by_user_id: uuid.UUID,
    ) -> RecertificationRun:
        due_items = self.discover_due_control_tests(
            organization_id=organization_id,
            due_within_days=due_within_days,
            limit=limit,
        )

        run = self._create_run(
            organization_id=organization_id,
            policy_id=None,
            run_type="control_reassessment",
            dry_run=dry_run,
            created_by_user_id=created_by_user_id,
        )
        run.due_count = len(due_items)
        run.overdue_count = sum(1 for item in due_items if item["due_status"] == "overdue")

        created = 0
        skipped = 0
        emails = 0
        errors = 0

        for item in due_items:
            due_marker = self._to_utc(item["next_due_at"]).isoformat() if item["next_due_at"] else item["due_status"]
            idem = self._build_control_idempotency_key(
                organization_id=organization_id,
                test_id=item["test_id"],
                due_marker=due_marker,
            )
            log_idem = f"{idem}:dryrun" if dry_run else idem

            if not dry_run and self._existing_created_action(organization_id, idem) is not None:
                self._log_action(
                    organization_id=organization_id,
                    run_id=run.id,
                    policy_id=None,
                    entity_type="control_test_definition",
                    entity_id=item["test_id"],
                    action_type="create_reassessment_task",
                    action_status="skipped_duplicate",
                    idempotency_key=f"{idem}:skip:{run.id}",
                    skipped_reason="Duplicate idempotency key already created",
                )
                skipped += 1
                continue

            try:
                task = None
                outbox_id = None
                if not dry_run:
                    priority = "high" if item["due_status"] == "overdue" else "normal"
                    task = Task(
                        organization_id=organization_id,
                        title=f"Reassess control: {item['control_title']}",
                        description=f"Control test '{item['test_name']}' is {item['due_status']}.",
                        status="open",
                        priority=priority,
                        task_type="control_remediation",
                        owner_user_id=item["owner_user_id"],
                        created_by_user_id=created_by_user_id,
                        linked_entity_type="control",
                        linked_entity_id=item["control_id"],
                        source="control_workflow",
                        reminder_status="none",
                        metadata_json={"run_id": str(run.id), "test_id": str(item["test_id"]), "due_status": item["due_status"]},
                    )
                    self.db.add(task)
                    self.db.flush()

                    if notify_owner:
                        outbox_id = self._queue_owner_email(
                            organization_id=organization_id,
                            created_by_user_id=created_by_user_id,
                            owner_user_id=item["owner_user_id"],
                            task_title=task.title,
                        )

                self._log_action(
                    organization_id=organization_id,
                    run_id=run.id,
                    policy_id=None,
                    entity_type="control_test_definition",
                    entity_id=item["test_id"],
                    action_type="create_reassessment_task",
                    action_status="would_create" if dry_run else "created",
                    idempotency_key=log_idem,
                    created_task_id=task.id if task else None,
                    created_email_outbox_id=outbox_id,
                    skipped_reason=("No valid recipient" if notify_owner and outbox_id is None and item["owner_user_id"] else None),
                )
                if notify_owner and outbox_id:
                    emails += 1
                created += 1
            except Exception as exc:
                self._log_action(
                    organization_id=organization_id,
                    run_id=run.id,
                    policy_id=None,
                    entity_type="control_test_definition",
                    entity_id=item["test_id"],
                    action_type="create_reassessment_task",
                    action_status="failed",
                    idempotency_key=(f"{idem}:error:{run.id}" if not dry_run else log_idem),
                    error_message=str(exc),
                )
                errors += 1

        run.task_count = created
        run.email_count = emails
        run.skipped_duplicate_count = skipped
        run.error_count = errors
        run.finished_at = self.now()
        run.status = "completed_with_errors" if errors else "completed"
        run.summary_json = {
            "due_count": run.due_count,
            "overdue_count": run.overdue_count,
            "task_count": run.task_count,
            "email_count": run.email_count,
            "skipped_duplicate_count": run.skipped_duplicate_count,
            "error_count": run.error_count,
            "dry_run": dry_run,
        }
        self.db.flush()
        return run

    def summary(self, organization_id: uuid.UUID) -> dict[str, int]:
        now = self.now()
        since = now - timedelta(hours=24)

        active_policies = int(
            self.db.execute(
                select(func.count(EvidenceRecertificationPolicy.id)).where(
                    EvidenceRecertificationPolicy.organization_id == organization_id,
                    EvidenceRecertificationPolicy.status == "active",
                )
            ).scalar_one()
        )

        due_evidence = int(
            self.db.execute(
                select(func.count(EvidenceItem.id)).where(
                    EvidenceItem.organization_id == organization_id,
                    EvidenceItem.status == "active",
                    or_(
                        EvidenceItem.freshness_status == "expired",
                        EvidenceItem.review_status.in_(["not_reviewed", "needs_review"]),
                    ),
                )
            ).scalar_one()
        )

        expired_evidence = int(
            self.db.execute(
                select(func.count(EvidenceItem.id)).where(
                    EvidenceItem.organization_id == organization_id,
                    EvidenceItem.status == "active",
                    EvidenceItem.freshness_status == "expired",
                )
            ).scalar_one()
        )

        evidence_needing_review = int(
            self.db.execute(
                select(func.count(EvidenceItem.id)).where(
                    EvidenceItem.organization_id == organization_id,
                    EvidenceItem.status == "active",
                    EvidenceItem.review_status.in_(["not_reviewed", "needs_review"]),
                )
            ).scalar_one()
        )

        due_control_tests = int(
            self.db.execute(
                select(func.count(ControlTestDefinition.id)).where(
                    ControlTestDefinition.organization_id == organization_id,
                    ControlTestDefinition.status == "active",
                    ControlTestDefinition.next_due_at.is_not(None),
                    ControlTestDefinition.next_due_at <= now + timedelta(days=7),
                )
            ).scalar_one()
        )

        overdue_control_tests = int(
            self.db.execute(
                select(func.count(ControlTestDefinition.id)).where(
                    ControlTestDefinition.organization_id == organization_id,
                    ControlTestDefinition.status == "active",
                    ControlTestDefinition.next_due_at.is_not(None),
                    ControlTestDefinition.next_due_at < now,
                )
            ).scalar_one()
        )

        runs_last_24h = int(
            self.db.execute(
                select(func.count(RecertificationRun.id)).where(
                    RecertificationRun.organization_id == organization_id,
                    RecertificationRun.created_at >= since,
                )
            ).scalar_one()
        )

        tasks_created_last_24h = int(
            self.db.execute(
                select(func.count(RecertificationActionLog.id)).where(
                    RecertificationActionLog.organization_id == organization_id,
                    RecertificationActionLog.created_at >= since,
                    RecertificationActionLog.action_status == "created",
                    RecertificationActionLog.action_type.in_(["create_recertification_task", "create_reassessment_task"]),
                )
            ).scalar_one()
        )

        duplicates_skipped_last_24h = int(
            self.db.execute(
                select(func.count(RecertificationActionLog.id)).where(
                    RecertificationActionLog.organization_id == organization_id,
                    RecertificationActionLog.created_at >= since,
                    RecertificationActionLog.action_status == "skipped_duplicate",
                )
            ).scalar_one()
        )

        return {
            "active_policies": active_policies,
            "due_evidence": due_evidence,
            "expired_evidence": expired_evidence,
            "evidence_needing_review": evidence_needing_review,
            "due_control_tests": due_control_tests,
            "overdue_control_tests": overdue_control_tests,
            "runs_last_24h": runs_last_24h,
            "tasks_created_last_24h": tasks_created_last_24h,
            "duplicates_skipped_last_24h": duplicates_skipped_last_24h,
        }
