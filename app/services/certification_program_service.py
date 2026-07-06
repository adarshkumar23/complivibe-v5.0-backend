from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.certification_program import CertificationProgram
from app.models.certification_program_activation import CertificationProgramActivation
from app.models.compliance_deadline import ComplianceDeadline
from app.models.framework import Framework
from app.models.organization_framework import OrganizationFramework
from app.models.task import Task
from app.models.user import User
from app.schemas.certification_program import (
    CertificationProgramActivateResponse,
    CertificationProgramProgressResponse,
    CertificationProgramWeekProgress,
)
from app.services.audit_service import AuditService
from app.services.task_service import TaskService


PROGRAM_SEEDS: list[dict] = [
    {
        "name": "SOC2-TypeI-8wk",
        "target_framework": "SOC2",
        "duration_weeks": 8,
        "description": "Eight-week SOC 2 Type I readiness sprint with control, evidence, and review milestones.",
    },
    {
        "name": "GDPR-Baseline-30day",
        "target_framework": "GDPR",
        "duration_weeks": 4,
        "description": "Four-week GDPR baseline program for core privacy governance and records.",
    },
    {
        "name": "ISO27001-6mo",
        "target_framework": "ISO_27001",
        "duration_weeks": 24,
        "description": "Six-month ISO 27001 implementation cadence with staged control deployment.",
    },
    {
        "name": "DPDP-Ready-45day",
        "target_framework": "INDIA_DPDP",
        "duration_weeks": 7,
        "description": "Forty-five day DPDP readiness program for notice, consent, and breach controls.",
    },
    {
        "name": "EU-AI-Act-HighRisk-12wk",
        "target_framework": "EU_AI_ACT",
        "duration_weeks": 12,
        "description": "Twelve-week high-risk AI governance launch for policy, controls, and evidence.",
    },
]


def _build_weeks(duration_weeks: int) -> list[dict]:
    rows: list[dict] = []
    for week in range(1, duration_weeks + 1):
        week_start_day = (week - 1) * 7
        rows.append(
            {
                "week_number": week,
                "tasks": [
                    {
                        "title": f"Week {week}: policy and control workplan",
                        "description": f"Execute week {week} planned control actions and evidence checkpoints.",
                        "due_in_days": week_start_day + 6,
                    }
                ],
                "evidence_requests": [
                    {
                        "title": f"Week {week}: evidence submission pack",
                        "description": f"Submit evidence requested for week {week} control scope.",
                        "due_in_days": week_start_day + 6,
                    }
                ],
                "deadlines": [
                    {
                        "title": f"Week {week}: completion milestone",
                        "description": f"Weekly certification milestone for week {week}.",
                        "due_in_days": week_start_day + 6,
                        "priority": "medium",
                    }
                ],
            }
        )
    return rows


def _build_evidence_templates(name: str) -> list[dict]:
    return [
        {"template_key": "policy_approval", "label": f"{name} policy approval evidence"},
        {"template_key": "control_test_result", "label": f"{name} control test output"},
        {"template_key": "artifact_register", "label": f"{name} artifact register snapshot"},
    ]


class CertificationProgramService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.task_service = TaskService(db)
        self.audit = AuditService(db)

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def utcdate() -> date:
        return datetime.now(UTC).date()

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def ensure_seed_programs(self) -> None:
        existing = {
            row.name: row
            for row in self.db.execute(
                select(CertificationProgram).where(CertificationProgram.status != "archived")
            ).scalars().all()
        }
        for row in PROGRAM_SEEDS:
            weeks = _build_weeks(int(row["duration_weeks"]))
            prerequisites = {"required_framework_codes": [row["target_framework"]]}
            evidence_templates = _build_evidence_templates(str(row["name"]))
            if row["name"] not in existing:
                self.db.add(
                    CertificationProgram(
                        name=row["name"],
                        target_framework=row["target_framework"],
                        duration_weeks=row["duration_weeks"],
                        weeks_json=weeks,
                        prerequisites_json=prerequisites,
                        evidence_templates_json=evidence_templates,
                        description=row["description"],
                        status="active",
                    )
                )
            else:
                current = existing[row["name"]]
                current.target_framework = row["target_framework"]
                current.duration_weeks = row["duration_weeks"]
                current.weeks_json = weeks
                current.prerequisites_json = prerequisites
                current.evidence_templates_json = evidence_templates
                current.description = row["description"]
                current.status = "active"
        self.db.flush()

    def list_programs(self) -> list[CertificationProgram]:
        self.ensure_seed_programs()
        return self.db.execute(
            select(CertificationProgram)
            .where(CertificationProgram.status == "active")
            .order_by(CertificationProgram.name.asc())
        ).scalars().all()

    def require_program(self, program_id: uuid.UUID) -> CertificationProgram:
        self.ensure_seed_programs()
        row = self.db.execute(
            select(CertificationProgram).where(
                CertificationProgram.id == program_id,
                CertificationProgram.status == "active",
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Certification program not found")
        return row

    def activate_program(
        self,
        *,
        organization_id: uuid.UUID,
        program_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        owner_user_id: uuid.UUID | None,
    ) -> CertificationProgramActivateResponse:
        program = self.require_program(program_id)
        owner_user = self.task_service.ensure_owner_is_active_member(organization_id, owner_user_id or actor_user_id)
        if owner_user is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to resolve activation owner")

        existing = self.db.execute(
            select(CertificationProgramActivation).where(
                CertificationProgramActivation.organization_id == organization_id,
                CertificationProgramActivation.certification_program_id == program.id,
            )
        ).scalar_one_or_none()
        if existing is not None and existing.status == "active":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Certification program already active")

        now = self.utcnow()
        projected_completion = self.utcdate() + timedelta(days=max(1, int(program.duration_weeks)) * 7)

        if existing is None:
            activation = CertificationProgramActivation(
                organization_id=organization_id,
                certification_program_id=program.id,
                status="active",
                activated_by_user_id=actor_user_id,
                activated_at=now,
                projected_completion_date=projected_completion,
                completed_at=None,
                metadata_json={"program_name": program.name},
            )
            self.db.add(activation)
            self.db.flush()
        else:
            existing.status = "active"
            existing.activated_by_user_id = actor_user_id
            existing.activated_at = now
            existing.projected_completion_date = projected_completion
            existing.completed_at = None
            existing.metadata_json = {"program_name": program.name}
            activation = existing
            self.db.flush()

        self.audit.write_audit_log(
            action="certification_program.activated",
            entity_type="certification_program_activation",
            entity_id=activation.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            after_json={
                "certification_program_id": str(program.id),
                "status": activation.status,
                "projected_completion_date": str(projected_completion),
            },
            metadata_json={"source": "api"},
        )

        created_tasks = 0
        created_evidence_requests = 0
        created_deadlines = 0
        for week in list(program.weeks_json or []):
            week_number = int(week.get("week_number", 0))
            for task_payload in list(week.get("tasks") or []):
                due_days = max(1, int(task_payload.get("due_in_days", week_number * 7)))
                task = Task(
                    organization_id=organization_id,
                    title=str(task_payload["title"]),
                    description=str(task_payload.get("description") or ""),
                    status="open",
                    priority="normal",
                    task_type="certification_task",
                    owner_user_id=owner_user.id,
                    created_by_user_id=actor_user_id,
                    due_date=now + timedelta(days=due_days),
                    linked_entity_type="certification_program",
                    linked_entity_id=activation.id,
                    source="automation",
                    reminder_status="none",
                    metadata_json={"week_number": week_number, "program_id": str(program.id), "program_name": program.name},
                )
                self.db.add(task)
                self.db.flush()
                created_tasks += 1
                self.audit.write_audit_log(
                    action="certification_program.task_created",
                    entity_type="task",
                    entity_id=task.id,
                    organization_id=organization_id,
                    actor_user_id=actor_user_id,
                    after_json={"task_type": task.task_type, "week_number": week_number, "due_date": task.due_date.isoformat()},
                    metadata_json={"source": "program_activation", "activation_id": str(activation.id)},
                )

            for evidence_payload in list(week.get("evidence_requests") or []):
                due_days = max(1, int(evidence_payload.get("due_in_days", week_number * 7)))
                task = Task(
                    organization_id=organization_id,
                    title=str(evidence_payload["title"]),
                    description=str(evidence_payload.get("description") or ""),
                    status="open",
                    priority="high",
                    task_type="evidence_request",
                    owner_user_id=owner_user.id,
                    created_by_user_id=actor_user_id,
                    due_date=now + timedelta(days=due_days),
                    linked_entity_type="certification_program",
                    linked_entity_id=activation.id,
                    source="automation",
                    reminder_status="none",
                    metadata_json={"week_number": week_number, "program_id": str(program.id), "program_name": program.name},
                )
                self.db.add(task)
                self.db.flush()
                created_evidence_requests += 1
                self.audit.write_audit_log(
                    action="certification_program.evidence_request_created",
                    entity_type="task",
                    entity_id=task.id,
                    organization_id=organization_id,
                    actor_user_id=actor_user_id,
                    after_json={"task_type": task.task_type, "week_number": week_number, "due_date": task.due_date.isoformat()},
                    metadata_json={"source": "program_activation", "activation_id": str(activation.id)},
                )

            for deadline_payload in list(week.get("deadlines") or []):
                due_days = max(1, int(deadline_payload.get("due_in_days", week_number * 7)))
                deadline = ComplianceDeadline(
                    organization_id=organization_id,
                    title=str(deadline_payload["title"]),
                    description=str(deadline_payload.get("description") or ""),
                    deadline_type="certification_program",
                    due_date=(self.utcdate() + timedelta(days=due_days)),
                    status="upcoming",
                    priority=str(deadline_payload.get("priority") or "medium"),
                    owner_user_id=owner_user.id,
                    linked_entity_type="certification_program",
                    linked_entity_id=activation.id,
                    reminder_days_before=3,
                    created_by_user_id=actor_user_id,
                    tags_json={"week_number": week_number, "program_id": str(program.id), "program_name": program.name},
                    notes=None,
                )
                self.db.add(deadline)
                self.db.flush()
                created_deadlines += 1
                self.audit.write_audit_log(
                    action="certification_program.deadline_created",
                    entity_type="compliance_deadline",
                    entity_id=deadline.id,
                    organization_id=organization_id,
                    actor_user_id=actor_user_id,
                    after_json={"deadline_type": deadline.deadline_type, "week_number": week_number, "due_date": str(deadline.due_date)},
                    metadata_json={"source": "program_activation", "activation_id": str(activation.id)},
                )

        return CertificationProgramActivateResponse(
            activation_id=activation.id,
            certification_program_id=program.id,
            created_tasks=created_tasks,
            created_evidence_requests=created_evidence_requests,
            created_deadlines=created_deadlines,
            projected_completion_date=activation.projected_completion_date,
            status=activation.status,
        )

    def _framework_code_is_active(self, organization_id: uuid.UUID, framework_code: str) -> bool:
        framework = self.db.execute(select(Framework).where(Framework.code == framework_code)).scalar_one_or_none()
        if framework is None:
            return False
        active = self.db.execute(
            select(OrganizationFramework).where(
                OrganizationFramework.organization_id == organization_id,
                OrganizationFramework.framework_id == framework.id,
                OrganizationFramework.status == "active",
            )
        ).scalar_one_or_none()
        return active is not None

    def get_progress(self, *, organization_id: uuid.UUID, program_id: uuid.UUID) -> CertificationProgramProgressResponse:
        program = self.require_program(program_id)
        activation = self.db.execute(
            select(CertificationProgramActivation).where(
                CertificationProgramActivation.organization_id == organization_id,
                CertificationProgramActivation.certification_program_id == program.id,
            )
        ).scalar_one_or_none()
        if activation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Certification program activation not found")

        tasks = self.db.execute(
            select(Task).where(
                Task.organization_id == organization_id,
                Task.linked_entity_type == "certification_program",
                Task.linked_entity_id == activation.id,
                Task.cancelled_at.is_(None),
            )
        ).scalars().all()
        deadlines = self.db.execute(
            select(ComplianceDeadline).where(
                ComplianceDeadline.organization_id == organization_id,
                ComplianceDeadline.linked_entity_type == "certification_program",
                ComplianceDeadline.linked_entity_id == activation.id,
            )
        ).scalars().all()

        weekly_totals: dict[int, int] = defaultdict(int)
        weekly_completed: dict[int, int] = defaultdict(int)
        weekly_blockers: dict[int, list[str]] = defaultdict(list)
        now = self.utcnow()
        today = self.utcdate()

        for row in tasks:
            meta = row.metadata_json or {}
            week = int(meta.get("week_number", 0))
            if week <= 0:
                continue
            weekly_totals[week] += 1
            due_at = self._as_utc(row.due_date)
            if row.status == "completed":
                weekly_completed[week] += 1
            elif due_at is not None and due_at < now and row.status not in {"completed", "cancelled"}:
                weekly_blockers[week].append(f"Overdue task: {row.title}")

        for row in deadlines:
            tags = row.tags_json or {}
            week = int(tags.get("week_number", 0))
            if week <= 0:
                continue
            weekly_totals[week] += 1
            if row.status == "completed":
                weekly_completed[week] += 1
            elif row.due_date < today and row.status in {"upcoming", "overdue"}:
                weekly_blockers[week].append(f"Overdue deadline: {row.title}")

        weekly_progress: list[CertificationProgramWeekProgress] = []
        all_blockers: list[str] = []
        for week in sorted(set(list(weekly_totals.keys()) + [int(w.get("week_number", 0)) for w in (program.weeks_json or []) if int(w.get("week_number", 0)) > 0])):
            total = int(weekly_totals.get(week, 0))
            completed = int(weekly_completed.get(week, 0))
            pct = round((completed / total) * 100, 2) if total else 0.0
            blockers = weekly_blockers.get(week, [])
            all_blockers.extend(blockers)
            weekly_progress.append(
                CertificationProgramWeekProgress(
                    week_number=week,
                    total_items=total,
                    completed_items=completed,
                    completion_pct=pct,
                    blockers=blockers,
                )
            )

        prereq_blockers: list[str] = []
        prerequisites = program.prerequisites_json or {}
        required_codes = prerequisites.get("required_framework_codes") if isinstance(prerequisites, dict) else []
        for code in list(required_codes or []):
            if not self._framework_code_is_active(organization_id, str(code)):
                prereq_blockers.append(f"Required framework not active: {code}")

        all_blockers.extend(prereq_blockers)

        total_items = sum(item.total_items for item in weekly_progress)
        total_completed = sum(item.completed_items for item in weekly_progress)
        overall = round((total_completed / total_items) * 100, 2) if total_items else 0.0
        projected_on_track = len(all_blockers) == 0 and overall >= 50.0

        return CertificationProgramProgressResponse(
            certification_program_id=program.id,
            activation_id=activation.id,
            status=activation.status,
            activated_at=activation.activated_at,
            projected_completion_date=activation.projected_completion_date,
            overall_completion_pct=overall,
            projected_on_track=projected_on_track,
            blockers=all_blockers,
            weekly_progress=weekly_progress,
        )
