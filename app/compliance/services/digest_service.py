import uuid
from datetime import UTC, date, datetime, time, timedelta

from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.ai_governance.services.ai_provider_service import AIProviderService
from app.compliance.services.email_template_service import EmailTemplateService
from app.models.compliance_deadline import ComplianceDeadline
from app.models.digest_config import DigestConfig
from app.models.email_outbox import EmailOutbox
from app.models.evidence_item import EvidenceItem
from app.models.issue import Issue
from app.models.org_email_config import OrgEmailConfig
from app.models.organization import Organization
from app.models.risk import Risk
from app.models.task import Task
from app.models.user import User
from app.privacy.services.notification_preference_service import NotificationPreferenceService
from app.services.audit_service import AuditService


class DigestService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _as_utc_safe(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _parse_send_time(value: str) -> str:
        try:
            parts = value.split(":")
            hh = int(parts[0])
            mm = int(parts[1])
            _ = time(hour=hh, minute=mm)
            return f"{hh:02d}:{mm:02d}"
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid send_time_utc format") from exc

    @staticmethod
    def _priority_rank(priority: str) -> int:
        mapping = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        return mapping.get(str(priority).lower(), 4)

    @staticmethod
    def _escalate_task_overdue(days_overdue: int) -> str:
        # A task overdue by a couple of days is annoying; one overdue for weeks is a real
        # control failure risk. Escalate the notification priority, don't leave it flat.
        if days_overdue >= 14:
            return "critical"
        if days_overdue >= 3:
            return "high"
        return "medium"

    @staticmethod
    def _escalate_deadline_upcoming(days_remaining: int) -> str:
        if days_remaining <= 2:
            return "critical"
        if days_remaining <= 7:
            return "high"
        return "medium"

    @staticmethod
    def _escalate_evidence_expiring(days_remaining: int) -> str:
        if days_remaining <= 3:
            return "high"
        return "medium"

    def _ranked_event_items(
        self,
        *,
        overdue_tasks: list[dict],
        open_risks: list[dict],
        upcoming_deadlines: list[dict],
        expiring_evidence: list[dict],
    ) -> list[dict]:
        rows: list[dict] = []
        for task in overdue_tasks:
            days_overdue = int(task.get("days_overdue") or 0)
            rows.append(
                {
                    "event_type": "task_overdue",
                    "priority_rank": self._priority_rank(self._escalate_task_overdue(days_overdue)),
                    "urgency_score": days_overdue,
                    "title": str(task.get("title") or "Overdue task"),
                    "detail": f"{days_overdue} day(s) overdue",
                }
            )
        for risk in open_risks:
            rows.append(
                {
                    "event_type": "risk_open",
                    "priority_rank": self._priority_rank(str(risk.get("severity") or "high")),
                    "urgency_score": 0,
                    "title": str(risk.get("title") or "Open risk"),
                    "detail": f"severity={risk.get('severity', 'high')}",
                }
            )
        for deadline in upcoming_deadlines:
            days_remaining = int(deadline.get("days_remaining") or 0)
            rows.append(
                {
                    "event_type": "deadline_upcoming",
                    "priority_rank": self._priority_rank(self._escalate_deadline_upcoming(days_remaining)),
                    "urgency_score": max(0, 30 - days_remaining),
                    "title": str(deadline.get("title") or "Upcoming deadline"),
                    "detail": f"due in {days_remaining} day(s)",
                }
            )
        for evidence in expiring_evidence:
            days_remaining = int(evidence.get("days_remaining") or 0)
            rows.append(
                {
                    "event_type": "evidence_expiring",
                    "priority_rank": self._priority_rank(self._escalate_evidence_expiring(days_remaining)),
                    "urgency_score": max(0, 30 - days_remaining),
                    "title": str(evidence.get("title") or "Expiring evidence"),
                    "detail": f"{days_remaining} day(s) remaining",
                }
            )
        # Within the same priority tier, surface the most urgent (highest urgency_score) first;
        # title is only a final tiebreaker for deterministic ordering.
        rows.sort(key=lambda item: (int(item.get("priority_rank", 9)), -int(item.get("urgency_score", 0)), str(item.get("title") or "")))
        return rows

    def _generate_digest_narrative(
        self,
        *,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        ranked_events: list[dict],
    ) -> tuple[str, str, list[str]]:
        if not ranked_events:
            return (
                "No urgent changes were detected in your compliance workload today; keep current controls and evidence collection cadence steady.",
                "deterministic_empty",
                [],
            )

        event_lines = [f"- {item['event_type']}: {item['title']} ({item['detail']})" for item in ranked_events[:6]]
        messages = [
            {
                "role": "system",
                "content": (
                    "You write one concise compliance operations digest paragraph. "
                    "Prioritize urgent items first, mention likely impact, and end with a concrete next-step focus. "
                    "Do not use bullet points."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Organization={org_id}; user={user_id}. "
                    "Create exactly one paragraph (2-4 sentences) from these prioritized events:\n"
                    + "\n".join(event_lines)
                ),
            },
        ]
        staleness_flags: list[str] = []
        try:
            narrative, provider_name, _ = AIProviderService(self.db)._run_provider_chain(
                org_id=org_id,
                messages=messages,
                failure_context="Digest narrative generation unavailable",
            )
            paragraph = " ".join(str(narrative).strip().split())
            if not paragraph:
                raise RuntimeError("empty narrative")
            return paragraph, f"ai_{provider_name}", staleness_flags
        except Exception:
            staleness_flags.append("ai_narrative_fallback")
            first = ranked_events[0]
            fallback = (
                f"Top priority is {first['title']} ({first['detail']}); focus first on remediating this before other items. "
                f"There are {len(ranked_events)} prioritized signals across tasks, risks, evidence, and deadlines to review today."
            )
            return fallback, "deterministic_fallback", staleness_flags

    @staticmethod
    def _clamp_score(value: float) -> int:
        return max(0, min(100, int(round(value))))

    def _weekly_progress_metrics(
        self,
        *,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        start_at: datetime,
        end_at: datetime,
    ) -> dict[str, int]:
        tasks_completed = int(
            self.db.execute(
                select(func.count(Task.id)).where(
                    Task.organization_id == org_id,
                    Task.owner_user_id == user_id,
                    Task.completed_at.is_not(None),
                    Task.completed_at >= start_at,
                    Task.completed_at < end_at,
                )
            ).scalar_one()
            or 0
        )
        evidence_reviewed = int(
            self.db.execute(
                select(func.count(EvidenceItem.id)).where(
                    EvidenceItem.organization_id == org_id,
                    EvidenceItem.reviewed_at.is_not(None),
                    EvidenceItem.reviewed_at >= start_at,
                    EvidenceItem.reviewed_at < end_at,
                )
            ).scalar_one()
            or 0
        )
        deadlines_completed = int(
            self.db.execute(
                select(func.count(ComplianceDeadline.id)).where(
                    ComplianceDeadline.organization_id == org_id,
                    ComplianceDeadline.owner_user_id == user_id,
                    ComplianceDeadline.completed_at.is_not(None),
                    ComplianceDeadline.completed_at >= start_at,
                    ComplianceDeadline.completed_at < end_at,
                )
            ).scalar_one()
            or 0
        )
        issues_opened = int(
            self.db.execute(
                select(func.count(Issue.id)).where(
                    Issue.organization_id == org_id,
                    Issue.created_at >= start_at,
                    Issue.created_at < end_at,
                    Issue.deleted_at.is_(None),
                )
            ).scalar_one()
            or 0
        )
        issues_resolved = int(
            self.db.execute(
                select(func.count(Issue.id)).where(
                    Issue.organization_id == org_id,
                    Issue.deleted_at.is_(None),
                    (
                        (Issue.resolved_at.is_not(None) & (Issue.resolved_at >= start_at) & (Issue.resolved_at < end_at))
                        | (Issue.closed_at.is_not(None) & (Issue.closed_at >= start_at) & (Issue.closed_at < end_at))
                    ),
                )
            ).scalar_one()
            or 0
        )
        return {
            "tasks_completed": tasks_completed,
            "evidence_reviewed": evidence_reviewed,
            "deadlines_completed": deadlines_completed,
            "issues_opened": issues_opened,
            "issues_resolved": issues_resolved,
        }

    def _weekly_compliance_score(self, metrics: dict[str, int]) -> int:
        score = (
            50
            + (2 * int(metrics.get("tasks_completed", 0)))
            + (2 * int(metrics.get("issues_resolved", 0)))
            + (1 * int(metrics.get("evidence_reviewed", 0)))
            + (1 * int(metrics.get("deadlines_completed", 0)))
            - (3 * int(metrics.get("issues_opened", 0)))
        )
        return self._clamp_score(score)

    def _weekly_wins_and_priorities(
        self,
        *,
        current_metrics: dict[str, int],
        previous_metrics: dict[str, int],
    ) -> tuple[list[str], list[str]]:
        wins: list[tuple[int, str]] = []
        priorities: list[tuple[int, str]] = []

        def _delta(name: str) -> int:
            return int(current_metrics.get(name, 0)) - int(previous_metrics.get(name, 0))

        tasks_delta = _delta("tasks_completed")
        if tasks_delta > 0:
            wins.append((tasks_delta, f"Completed {tasks_delta} more tasks than last week."))
        elif tasks_delta < 0:
            priorities.append((abs(tasks_delta), f"Task completion dropped by {abs(tasks_delta)} compared with last week."))

        reviewed_delta = _delta("evidence_reviewed")
        if reviewed_delta > 0:
            wins.append((reviewed_delta, f"Reviewed {reviewed_delta} additional evidence items week-over-week."))
        elif reviewed_delta < 0:
            priorities.append((abs(reviewed_delta), f"Evidence reviews fell by {abs(reviewed_delta)} week-over-week."))

        deadlines_delta = _delta("deadlines_completed")
        if deadlines_delta > 0:
            wins.append((deadlines_delta, f"Closed {deadlines_delta} more deadlines than last week."))
        elif deadlines_delta < 0:
            priorities.append((abs(deadlines_delta), f"Completed {abs(deadlines_delta)} fewer deadlines than last week."))

        resolved_delta = _delta("issues_resolved")
        if resolved_delta > 0:
            wins.append((resolved_delta, f"Resolved {resolved_delta} more issues than last week."))
        elif resolved_delta < 0:
            priorities.append((abs(resolved_delta), f"Issue resolution decreased by {abs(resolved_delta)} week-over-week."))

        opened_delta = _delta("issues_opened")
        if opened_delta < 0:
            wins.append((abs(opened_delta), f"New issues reduced by {abs(opened_delta)} week-over-week."))
        elif opened_delta > 0:
            priorities.append((opened_delta, f"New issues increased by {opened_delta} week-over-week."))

        wins.sort(key=lambda item: item[0], reverse=True)
        priorities.sort(key=lambda item: item[0], reverse=True)
        top_wins = [item[1] for item in wins[:3]] or ["No measurable improvements over the previous week."]
        top_priorities = [item[1] for item in priorities[:3]] or ["No material regressions detected this week."]
        return top_wins, top_priorities

    def _generate_weekly_progress_narrative(
        self,
        *,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        score_current: int,
        score_delta: int,
        top_wins: list[str],
        top_priorities: list[str],
    ) -> tuple[str, str, list[str]]:
        staleness_flags: list[str] = []
        messages = [
            {
                "role": "system",
                "content": (
                    "You write one concise weekly compliance progress paragraph for operations leadership. "
                    "Use plain language and quantify changes where possible. "
                    "Prioritize biggest win and biggest priority next week."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Organization={org_id}; user={user_id}; weekly_score={score_current}; score_delta={score_delta}. "
                    f"Top wins={top_wins}. Top priorities={top_priorities}. "
                    "Return exactly one paragraph, 3-4 sentences."
                ),
            },
        ]
        try:
            narrative, provider_name, _ = AIProviderService(self.db)._run_provider_chain(
                org_id=org_id,
                messages=messages,
                failure_context="Weekly progress narrative generation unavailable",
            )
            paragraph = " ".join(str(narrative).strip().split())
            if not paragraph:
                raise RuntimeError("empty weekly narrative")
            return paragraph, f"ai_{provider_name}", staleness_flags
        except Exception:
            staleness_flags.append("ai_weekly_narrative_fallback")
            win = top_wins[0] if top_wins else "No measurable improvements this week."
            priority = top_priorities[0] if top_priorities else "No major blockers were identified."
            fallback = (
                f"Weekly compliance score is {score_current} ({score_delta:+d} versus last week). "
                f"Top win: {win} Top priority for next week: {priority}"
            )
            return fallback, "deterministic_fallback", staleness_flags

    def get_or_create_configs(self, org_id: uuid.UUID, user_id: uuid.UUID) -> list[DigestConfig]:
        now = self.utcnow()
        defaults = [
            ("daily", "08:00", None),
            ("weekly", "08:00", 0),
        ]
        for digest_type, send_time_utc, send_day_of_week in defaults:
            row = self.db.execute(
                select(DigestConfig).where(
                    DigestConfig.organization_id == org_id,
                    DigestConfig.user_id == user_id,
                    DigestConfig.digest_type == digest_type,
                )
            ).scalar_one_or_none()
            if row is None:
                self.db.add(
                    DigestConfig(
                        organization_id=org_id,
                        user_id=user_id,
                        digest_type=digest_type,
                        is_enabled=True,
                        send_time_utc=send_time_utc,
                        send_day_of_week=send_day_of_week,
                        last_sent_at=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
        self.db.flush()
        return self.db.execute(
            select(DigestConfig)
            .where(DigestConfig.organization_id == org_id, DigestConfig.user_id == user_id)
            .order_by(DigestConfig.digest_type.asc())
        ).scalars().all()

    def update_daily_config(self, org_id: uuid.UUID, user_id: uuid.UUID, is_enabled: bool, send_time_utc: str) -> DigestConfig:
        self.get_or_create_configs(org_id, user_id)
        row = self.db.execute(
            select(DigestConfig).where(
                DigestConfig.organization_id == org_id,
                DigestConfig.user_id == user_id,
                DigestConfig.digest_type == "daily",
            )
        ).scalar_one()
        row.is_enabled = bool(is_enabled)
        row.send_time_utc = self._parse_send_time(send_time_utc)
        row.updated_at = self.utcnow()
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="digest.config_updated",
            entity_type="digest_config",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"digest_type": row.digest_type, "is_enabled": row.is_enabled, "send_time_utc": row.send_time_utc},
            metadata_json={"source": "api"},
        )
        return row

    def update_weekly_config(self, org_id: uuid.UUID, user_id: uuid.UUID, is_enabled: bool, send_day_of_week: int) -> DigestConfig:
        self.get_or_create_configs(org_id, user_id)
        row = self.db.execute(
            select(DigestConfig).where(
                DigestConfig.organization_id == org_id,
                DigestConfig.user_id == user_id,
                DigestConfig.digest_type == "weekly",
            )
        ).scalar_one()
        row.is_enabled = bool(is_enabled)
        row.send_day_of_week = int(send_day_of_week)
        row.updated_at = self.utcnow()
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="digest.config_updated",
            entity_type="digest_config",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"digest_type": row.digest_type, "is_enabled": row.is_enabled, "send_day_of_week": row.send_day_of_week},
            metadata_json={"source": "api"},
        )
        return row

    def build_daily_digest(self, org_id: uuid.UUID, user_id: uuid.UUID, db: Session | None = None) -> dict:
        _db = db or self.db
        now = self.utcnow()
        today = now.date()

        overdue_tasks = _db.execute(
            select(Task).where(
                Task.organization_id == org_id,
                Task.owner_user_id == user_id,
                Task.due_date.is_not(None),
                Task.due_date < now,
                Task.status.notin_(["completed", "cancelled"]),
            ).order_by(Task.due_date.asc()).limit(10)
        ).scalars().all()

        expiring_evidence = _db.execute(
            select(EvidenceItem).where(
                EvidenceItem.organization_id == org_id,
                EvidenceItem.valid_until.is_not(None),
                EvidenceItem.valid_until >= datetime.combine(today, time.min, tzinfo=UTC),
                EvidenceItem.valid_until <= datetime.combine(today + timedelta(days=30), time.max, tzinfo=UTC),
                EvidenceItem.status != "expired",
            ).order_by(EvidenceItem.valid_until.asc()).limit(10)
        ).scalars().all()

        open_risks = _db.execute(
            select(Risk).where(
                Risk.organization_id == org_id,
                Risk.owner_user_id == user_id,
                Risk.status.notin_(["closed", "accepted"]),
                Risk.severity.in_(["critical", "high"]),
            ).order_by(Risk.severity.asc()).limit(5)
        ).scalars().all()

        upcoming_deadlines = _db.execute(
            select(ComplianceDeadline).where(
                ComplianceDeadline.organization_id == org_id,
                ComplianceDeadline.owner_user_id == user_id,
                ComplianceDeadline.due_date >= today,
                ComplianceDeadline.due_date <= today + timedelta(days=14),
                ComplianceDeadline.status.notin_(["completed", "cancelled"]),
            ).order_by(ComplianceDeadline.due_date.asc()).limit(10)
        ).scalars().all()

        return {
            "digest_type": "daily",
            "generated_at": now.isoformat(),
            "user_id": str(user_id),
            "overdue_tasks": [
                {
                    "id": str(t.id),
                    "title": t.title,
                    "due_date": str(t.due_date.date()) if t.due_date else None,
                    "days_overdue": max(0, (today - t.due_date.date()).days) if t.due_date else 0,
                }
                for t in overdue_tasks
            ],
            "expiring_evidence": [
                {
                    "id": str(e.id),
                    "title": e.title,
                    "valid_until": str(e.valid_until.date()) if e.valid_until else None,
                    "days_remaining": max(0, (e.valid_until.date() - today).days) if e.valid_until else 0,
                }
                for e in expiring_evidence
            ],
            "open_risks": [
                {
                    "id": str(r.id),
                    "title": r.title,
                    "severity": r.severity,
                }
                for r in open_risks
            ],
            "upcoming_deadlines": [
                {
                    "id": str(d.id),
                    "title": d.title,
                    "due_date": str(d.due_date),
                    "days_remaining": (d.due_date - today).days,
                }
                for d in upcoming_deadlines
            ],
        }

    def _with_digest_narrative(self, *, org_id: uuid.UUID, user_id: uuid.UUID, payload: dict) -> dict:
        all_ranked_events = self._ranked_event_items(
            overdue_tasks=list(payload.get("overdue_tasks") or []),
            open_risks=list(payload.get("open_risks") or []),
            upcoming_deadlines=list(payload.get("upcoming_deadlines") or []),
            expiring_evidence=list(payload.get("expiring_evidence") or []),
        )
        total_signal_count = len(all_ranked_events)
        critical_items_count = sum(1 for item in all_ranked_events if int(item.get("priority_rank", 9)) == 0)
        ranked_events = all_ranked_events[:10]
        narrative, narrative_source, staleness_flags = self._generate_digest_narrative(
            org_id=org_id,
            user_id=user_id,
            ranked_events=ranked_events,
        )
        return {
            **payload,
            "prioritized_events": ranked_events,
            "total_signal_count": total_signal_count,
            "critical_items_count": critical_items_count,
            "items_truncated": total_signal_count > len(ranked_events),
            "narrative_paragraph": narrative,
            "narrative_source": narrative_source,
            "narrative_generated_at": self.utcnow().isoformat(),
            "data_staleness_flags": staleness_flags,
        }

    def build_weekly_digest(self, org_id: uuid.UUID, user_id: uuid.UUID, db: Session | None = None) -> dict:
        _db = db or self.db
        daily = self._with_digest_narrative(org_id=org_id, user_id=user_id, payload=self.build_daily_digest(org_id, user_id, _db))

        now = self.utcnow()
        week_ago = now - timedelta(days=7)
        previous_week_start = now - timedelta(days=14)
        today = now.date()
        month_end = date(today.year, today.month, 28) + timedelta(days=4)
        month_end = month_end - timedelta(days=month_end.day)

        new_issues = int(
            _db.execute(
                select(func.count(Issue.id)).where(
                    Issue.organization_id == org_id,
                    Issue.created_at >= week_ago,
                    Issue.deleted_at.is_(None),
                )
            ).scalar_one()
            or 0
        )

        obligations_due = int(
            _db.execute(
                select(func.count(ComplianceDeadline.id)).where(
                    ComplianceDeadline.organization_id == org_id,
                    ComplianceDeadline.due_date <= month_end,
                    ComplianceDeadline.due_date >= today,
                    ComplianceDeadline.status.notin_(["completed", "cancelled"]),
                )
            ).scalar_one()
            or 0
        )

        current_metrics = self._weekly_progress_metrics(
            org_id=org_id,
            user_id=user_id,
            start_at=week_ago,
            end_at=now,
        )
        previous_metrics = self._weekly_progress_metrics(
            org_id=org_id,
            user_id=user_id,
            start_at=previous_week_start,
            end_at=week_ago,
        )

        # An org younger than the 14-day comparison window has a fabricated all-zero
        # "previous week" -- any wins/priorities/score_delta computed against it are noise
        # (e.g. "reduced new issues" when there was no prior week to have issues in), not signal.
        org = _db.get(Organization, org_id)
        org_created_at = self._as_utc_safe(org.created_at) if org is not None else None
        insufficient_history = org_created_at is not None and org_created_at > previous_week_start

        current_score = self._weekly_compliance_score(current_metrics)
        previous_score = self._weekly_compliance_score(previous_metrics)
        score_delta = current_score - previous_score
        if insufficient_history:
            top_wins = ["Not enough account history yet for a week-over-week comparison."]
            top_priorities = ["Keep building activity this week; trend comparisons begin after two full weeks."]
        else:
            top_wins, top_priorities = self._weekly_wins_and_priorities(
                current_metrics=current_metrics,
                previous_metrics=previous_metrics,
            )
        weekly_narrative, weekly_narrative_source, weekly_staleness_flags = self._generate_weekly_progress_narrative(
            org_id=org_id,
            user_id=user_id,
            score_current=current_score,
            score_delta=score_delta,
            top_wins=top_wins,
            top_priorities=top_priorities,
        )
        if insufficient_history:
            weekly_staleness_flags.append("insufficient_history_for_comparison")

        return {
            **daily,
            "digest_type": "weekly",
            "new_issues_this_week": new_issues,
            "obligations_due_this_month": obligations_due,
            "score_current": current_score,
            "score_previous": previous_score,
            "score_delta": score_delta,
            "score_delta_meaningful": not insufficient_history,
            "top_3_wins": top_wins,
            "top_3_priorities": top_priorities,
            "weekly_metrics_current": current_metrics,
            "weekly_metrics_previous": previous_metrics,
            "weekly_window_start": week_ago.date().isoformat(),
            "weekly_window_end": now.date().isoformat(),
            "narrative_paragraph": weekly_narrative,
            "narrative_source": weekly_narrative_source,
            "narrative_generated_at": now.isoformat(),
            "data_staleness_flags": sorted(set(list(daily.get("data_staleness_flags") or []) + weekly_staleness_flags)),
        }

    def send_digest(self, org_id: uuid.UUID, user_id: uuid.UUID, digest_type: str, db: Session | None = None) -> bool:
        _db = db or self.db
        if digest_type not in {"daily", "weekly"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid digest type")

        if not NotificationPreferenceService(_db).should_notify(org_id, user_id, f"digest_{digest_type}"):
            return False

        cfg_active = _db.execute(
            select(OrgEmailConfig).where(
                OrgEmailConfig.organization_id == org_id,
                OrgEmailConfig.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if cfg_active is None:
            return False

        user = _db.get(User, user_id)
        if user is None or not user.email:
            return False
        org = _db.get(Organization, org_id)

        if digest_type == "daily":
            content = self._with_digest_narrative(
                org_id=org_id,
                user_id=user_id,
                payload=self.build_daily_digest(org_id, user_id, _db),
            )
        else:
            content = self.build_weekly_digest(org_id, user_id, _db)

        template_svc = EmailTemplateService()
        subject, html = template_svc.render(
            f"digest_{digest_type}.html",
            {
                "subject": f"Your {digest_type.title()} CompliVibe Digest",
                "user_name": user.full_name or user.email,
                **content,
            },
            org_name=org.name if org else "CompliVibe",
        )

        now = self.utcnow()
        _db.add(
            EmailOutbox(
                organization_id=org_id,
                template_id=None,
                event_type=f"digest.{digest_type}",
                template_name=f"digest_{digest_type}.html",
                template_context={
                    "subject": subject,
                    "user_name": user.full_name or user.email,
                    **content,
                },
                recipient_email=user.email,
                recipient_user_id=user.id,
                subject=subject,
                body_text=str(content.get("narrative_paragraph") or f"Your {digest_type} CompliVibe digest is ready."),
                body_html=html,
                status="pending",
                priority="normal",
                scheduled_at=None,
                queued_at=now,
                sent_at=None,
                failed_at=None,
                cancelled_at=None,
                locked_at=None,
                locked_by=None,
                lock_expires_at=None,
                last_attempt_at=None,
                next_attempt_at=None,
                dead_lettered_at=None,
                attempt_count=0,
                max_attempts=3,
                last_error=None,
                provider=None,
                provider_message_id=None,
                metadata_json={"source": "digest", "digest_type": digest_type},
                worker_metadata_json=None,
                created_by_user_id=None,
            )
        )
        _db.flush()

        AuditService(_db).write_audit_log(
            action="digest.sent",
            entity_type="email_outbox",
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"digest_type": digest_type, "recipient_user_id": str(user_id)},
            metadata_json={"source": "scheduler_or_manual"},
        )
        return True

    def _digest_configs_due(self, digest_type: str, now: datetime) -> list[DigestConfig]:
        rows = self.db.execute(
            select(DigestConfig).where(
                DigestConfig.digest_type == digest_type,
                DigestConfig.is_enabled.is_(True),
            )
        ).scalars().all()
        due: list[DigestConfig] = []
        for row in rows:
            if row.send_time_utc != "08:00":
                continue
            if digest_type == "weekly" and row.send_day_of_week not in (None, 0):
                continue
            if row.last_sent_at is not None and row.last_sent_at.date() >= now.date():
                continue
            due.append(row)
        return due

    def run_daily_digest_send(self) -> dict:
        now = self.utcnow()
        queued = 0
        skipped = 0
        processed = 0
        for row in self._digest_configs_due("daily", now):
            processed += 1
            if self.send_digest(row.organization_id, row.user_id, "daily", self.db):
                row.last_sent_at = now
                row.updated_at = now
                queued += 1
            else:
                skipped += 1
        self.db.flush()
        return {"processed": processed, "queued": queued, "skipped": skipped, "records_processed": processed}

    def run_weekly_digest_send(self) -> dict:
        now = self.utcnow()
        queued = 0
        skipped = 0
        processed = 0
        for row in self._digest_configs_due("weekly", now):
            processed += 1
            if self.send_digest(row.organization_id, row.user_id, "weekly", self.db):
                row.last_sent_at = now
                row.updated_at = now
                queued += 1
            else:
                skipped += 1
        self.db.flush()
        return {"processed": processed, "queued": queued, "skipped": skipped, "records_processed": processed}


def run_daily_digest_send_sweep(db: Session) -> dict:
    return DigestService(db).run_daily_digest_send()


def run_weekly_digest_send_sweep(db: Session) -> dict:
    return DigestService(db).run_weekly_digest_send()
