import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.control import Control
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.control_test_run import ControlTestRun
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.risk import Risk
from app.models.risk_control_link import RiskControlLink
from app.models.score_snapshot import ScoreSnapshot
from app.models.task import Task
from app.schemas.scoring import ScoreSummary

SNAPSHOT_TYPES = {
    "compliance_readiness",
    "evidence_readiness",
    "control_health",
    "risk_posture",
    "task_hygiene",
    "governance_health",
}


class ScoringService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _grade(score: int) -> str:
        if score >= 90:
            return "A"
        if score >= 80:
            return "B"
        if score >= 70:
            return "C"
        if score >= 60:
            return "D"
        return "F"

    @staticmethod
    def _clamp_score(raw: float) -> int:
        return int(max(0, min(100, round(raw))))

    def get_placeholder_score(self) -> ScoreSummary:
        return ScoreSummary(score=0, captured_at=self.now())

    def _active_controls_count(self, organization_id: uuid.UUID) -> int:
        return int(
            self.db.execute(
                select(func.count(Control.id)).where(
                    Control.organization_id == organization_id,
                    Control.status != "archived",
                )
            ).scalar_one()
        )

    def _latest_runs_by_control(self, organization_id: uuid.UUID) -> dict[uuid.UUID, ControlTestRun]:
        rows = self.db.execute(
            select(ControlTestRun)
            .where(ControlTestRun.organization_id == organization_id)
            .order_by(ControlTestRun.created_at.desc())
        ).scalars().all()

        by_control: dict[uuid.UUID, ControlTestRun] = {}
        for row in rows:
            if row.control_id not in by_control:
                by_control[row.control_id] = row
        return by_control

    def compute_control_health(self, organization_id: uuid.UUID) -> dict:
        active_controls = self._active_controls_count(organization_id)
        implemented_controls = int(
            self.db.execute(
                select(func.count(Control.id)).where(
                    Control.organization_id == organization_id,
                    Control.status == "implemented",
                )
            ).scalar_one()
        )
        controls_needing_review = int(
            self.db.execute(
                select(func.count(Control.id)).where(
                    Control.organization_id == organization_id,
                    Control.status == "needs_review",
                )
            ).scalar_one()
        )

        latest_runs = self._latest_runs_by_control(organization_id)
        controls_with_passing_latest_test = sum(1 for run in latest_runs.values() if run.result == "passed")
        controls_with_failed_latest_test = sum(1 for run in latest_runs.values() if run.result == "failed")

        if active_controls == 0:
            score = 0
        else:
            implemented_ratio = implemented_controls / active_controls
            passing_ratio = controls_with_passing_latest_test / active_controls
            needs_review_ratio = controls_needing_review / active_controls
            score = self._clamp_score((implemented_ratio * 0.55 + passing_ratio * 0.45 - needs_review_ratio * 0.2) * 100)

        inputs = {
            "active_controls": active_controls,
            "implemented_controls": implemented_controls,
            "controls_with_passing_latest_test": controls_with_passing_latest_test,
            "controls_with_failed_latest_test": controls_with_failed_latest_test,
            "controls_needing_review": controls_needing_review,
        }
        breakdown = {
            "implemented_ratio": round((implemented_controls / active_controls) if active_controls else 0, 4),
            "latest_test_pass_ratio": round((controls_with_passing_latest_test / active_controls) if active_controls else 0, 4),
            "needs_review_ratio": round((controls_needing_review / active_controls) if active_controls else 0, 4),
            "weights": {
                "implemented_ratio": 0.55,
                "latest_test_pass_ratio": 0.45,
                "needs_review_penalty": -0.2,
            },
        }
        recommendations = []
        if controls_with_failed_latest_test > 0:
            recommendations.append("Review controls with failed latest tests and assign remediation tasks.")
        if controls_needing_review > 0:
            recommendations.append("Resolve controls marked needs_review to improve control health.")

        return {
            "snapshot_type": "control_health",
            "score": score,
            "grade": self._grade(score),
            "inputs_json": inputs,
            "breakdown_json": breakdown,
            "recommendations_json": recommendations or None,
        }

    def compute_evidence_readiness(self, organization_id: uuid.UUID) -> dict:
        active_controls = self._active_controls_count(organization_id)

        controls_with_verified_current_evidence = int(
            self.db.execute(
                select(func.count(func.distinct(EvidenceControlLink.control_id)))
                .join(EvidenceItem, EvidenceItem.id == EvidenceControlLink.evidence_item_id)
                .where(
                    EvidenceControlLink.organization_id == organization_id,
                    EvidenceControlLink.link_status == "active",
                    EvidenceItem.organization_id == organization_id,
                    EvidenceItem.status == "active",
                    EvidenceItem.review_status == "verified",
                    EvidenceItem.freshness_status.in_(["current", "expiring_soon"]),
                )
            ).scalar_one()
        )

        controls_with_expired_evidence = int(
            self.db.execute(
                select(func.count(func.distinct(EvidenceControlLink.control_id)))
                .join(EvidenceItem, EvidenceItem.id == EvidenceControlLink.evidence_item_id)
                .where(
                    EvidenceControlLink.organization_id == organization_id,
                    EvidenceControlLink.link_status == "active",
                    EvidenceItem.organization_id == organization_id,
                    EvidenceItem.status == "active",
                    EvidenceItem.freshness_status == "expired",
                )
            ).scalar_one()
        )

        total_active_evidence = int(
            self.db.execute(
                select(func.count(EvidenceItem.id)).where(
                    EvidenceItem.organization_id == organization_id,
                    EvidenceItem.status == "active",
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

        if active_controls == 0:
            score = 0
        else:
            verified_ratio = controls_with_verified_current_evidence / active_controls
            expired_ratio = controls_with_expired_evidence / active_controls
            needs_review_ratio = (evidence_needing_review / total_active_evidence) if total_active_evidence else 0
            score = self._clamp_score((verified_ratio * 100) - (expired_ratio * 35) - (needs_review_ratio * 20))

        inputs = {
            "active_controls": active_controls,
            "controls_with_verified_current_evidence": controls_with_verified_current_evidence,
            "controls_with_expired_evidence": controls_with_expired_evidence,
            "total_active_evidence": total_active_evidence,
            "evidence_needing_review": evidence_needing_review,
        }
        breakdown = {
            "verified_coverage_ratio": round((controls_with_verified_current_evidence / active_controls) if active_controls else 0, 4),
            "expired_control_ratio": round((controls_with_expired_evidence / active_controls) if active_controls else 0, 4),
            "needs_review_evidence_ratio": round((evidence_needing_review / total_active_evidence) if total_active_evidence else 0, 4),
            "formula": "verified_coverage*100 - expired_ratio*35 - needs_review_ratio*20",
        }
        recommendations = []
        if controls_with_expired_evidence > 0:
            recommendations.append("Refresh or replace expired evidence linked to active controls.")
        if evidence_needing_review > 0:
            recommendations.append("Review pending evidence to improve readiness confidence.")

        return {
            "snapshot_type": "evidence_readiness",
            "score": score,
            "grade": self._grade(score),
            "inputs_json": inputs,
            "breakdown_json": breakdown,
            "recommendations_json": recommendations or None,
        }

    def compute_risk_posture(self, organization_id: uuid.UUID) -> dict:
        total_active_risks = int(
            self.db.execute(
                select(func.count(Risk.id)).where(
                    Risk.organization_id == organization_id,
                    Risk.status != "archived",
                )
            ).scalar_one()
        )

        critical_high_risks = int(
            self.db.execute(
                select(func.count(Risk.id)).where(
                    Risk.organization_id == organization_id,
                    Risk.status != "archived",
                    Risk.severity.in_(["critical", "high"]),
                )
            ).scalar_one()
        )

        risks_without_owner = int(
            self.db.execute(
                select(func.count(Risk.id)).where(
                    Risk.organization_id == organization_id,
                    Risk.status != "archived",
                    Risk.owner_user_id.is_(None),
                )
            ).scalar_one()
        )

        risks_with_controls = int(
            self.db.execute(
                select(func.count(func.distinct(RiskControlLink.risk_id))).where(
                    RiskControlLink.organization_id == organization_id,
                    RiskControlLink.status == "active",
                )
            ).scalar_one()
        )

        accepted_or_mitigated = int(
            self.db.execute(
                select(func.count(Risk.id)).where(
                    Risk.organization_id == organization_id,
                    Risk.status.in_(["accepted", "mitigated"]),
                )
            ).scalar_one()
        )

        if total_active_risks == 0:
            score = 100
        else:
            critical_high_ratio = critical_high_risks / total_active_risks
            without_owner_ratio = risks_without_owner / total_active_risks
            without_controls_ratio = max(0, (total_active_risks - risks_with_controls) / total_active_risks)
            accepted_or_mitigated_ratio = accepted_or_mitigated / total_active_risks
            score = self._clamp_score(
                100
                - (critical_high_ratio * 50)
                - (without_owner_ratio * 25)
                - (without_controls_ratio * 25)
                + (accepted_or_mitigated_ratio * 10)
            )

        inputs = {
            "total_active_risks": total_active_risks,
            "critical_high_risks": critical_high_risks,
            "risks_without_owner": risks_without_owner,
            "risks_without_controls": max(0, total_active_risks - risks_with_controls),
            "accepted_or_mitigated_risks": accepted_or_mitigated,
        }
        breakdown = {
            "critical_high_ratio": round((critical_high_risks / total_active_risks) if total_active_risks else 0, 4),
            "without_owner_ratio": round((risks_without_owner / total_active_risks) if total_active_risks else 0, 4),
            "without_controls_ratio": round((max(0, total_active_risks - risks_with_controls) / total_active_risks) if total_active_risks else 0, 4),
            "accepted_or_mitigated_ratio": round((accepted_or_mitigated / total_active_risks) if total_active_risks else 0, 4),
            "formula": "100 - critical_high*50 - without_owner*25 - without_controls*25 + accepted_or_mitigated*10",
        }
        recommendations = []
        if risks_without_owner > 0:
            recommendations.append("Assign risk owners for unowned active risks.")
        if (total_active_risks - risks_with_controls) > 0:
            recommendations.append("Map mitigating controls to uncovered active risks.")

        return {
            "snapshot_type": "risk_posture",
            "score": score,
            "grade": self._grade(score),
            "inputs_json": inputs,
            "breakdown_json": breakdown,
            "recommendations_json": recommendations or None,
        }

    def compute_task_hygiene(self, organization_id: uuid.UUID) -> dict:
        now = self.now()

        total_tasks = int(
            self.db.execute(select(func.count(Task.id)).where(Task.organization_id == organization_id)).scalar_one()
        )

        completed_tasks = int(
            self.db.execute(
                select(func.count(Task.id)).where(
                    Task.organization_id == organization_id,
                    Task.status == "completed",
                )
            ).scalar_one()
        )

        open_tasks = int(
            self.db.execute(
                select(func.count(Task.id)).where(
                    Task.organization_id == organization_id,
                    Task.status.in_(["open", "in_progress", "blocked"]),
                )
            ).scalar_one()
        )

        overdue_tasks = int(
            self.db.execute(
                select(func.count(Task.id)).where(
                    Task.organization_id == organization_id,
                    Task.status.in_(["open", "in_progress", "blocked"]),
                    Task.due_date.is_not(None),
                    Task.due_date < now,
                )
            ).scalar_one()
        )

        urgent_open_tasks = int(
            self.db.execute(
                select(func.count(Task.id)).where(
                    Task.organization_id == organization_id,
                    Task.status.in_(["open", "in_progress", "blocked"]),
                    Task.priority == "urgent",
                )
            ).scalar_one()
        )

        if total_tasks == 0:
            score = 100
        else:
            completion_ratio = completed_tasks / total_tasks
            overdue_ratio = (overdue_tasks / open_tasks) if open_tasks else 0
            urgent_ratio = (urgent_open_tasks / open_tasks) if open_tasks else 0
            score = self._clamp_score((completion_ratio * 0.6 + max(0, 1 - overdue_ratio) * 0.25 + max(0, 1 - urgent_ratio) * 0.15) * 100)

        inputs = {
            "total_tasks": total_tasks,
            "open_tasks": open_tasks,
            "overdue_tasks": overdue_tasks,
            "completed_tasks": completed_tasks,
            "urgent_open_tasks": urgent_open_tasks,
        }
        breakdown = {
            "completion_ratio": round((completed_tasks / total_tasks) if total_tasks else 0, 4),
            "overdue_open_ratio": round((overdue_tasks / open_tasks) if open_tasks else 0, 4),
            "urgent_open_ratio": round((urgent_open_tasks / open_tasks) if open_tasks else 0, 4),
            "formula": "completion*0.6 + (1-overdue_open)*0.25 + (1-urgent_open)*0.15",
        }
        recommendations = []
        if overdue_tasks > 0:
            recommendations.append("Prioritize overdue open tasks and rebalance due dates.")

        return {
            "snapshot_type": "task_hygiene",
            "score": score,
            "grade": self._grade(score),
            "inputs_json": inputs,
            "breakdown_json": breakdown,
            "recommendations_json": recommendations or None,
        }

    def compute_compliance_readiness(self, organization_id: uuid.UUID) -> dict:
        control_health = self.compute_control_health(organization_id)
        evidence_readiness = self.compute_evidence_readiness(organization_id)
        risk_posture = self.compute_risk_posture(organization_id)

        score = self._clamp_score(
            (control_health["score"] * 0.4)
            + (evidence_readiness["score"] * 0.4)
            + (risk_posture["score"] * 0.2)
        )
        breakdown = {
            "components": {
                "control_health": control_health["score"],
                "evidence_readiness": evidence_readiness["score"],
                "risk_posture": risk_posture["score"],
            },
            "weights": {
                "control_health": 0.4,
                "evidence_readiness": 0.4,
                "risk_posture": 0.2,
            },
        }
        recommendations = []
        for component in (control_health, evidence_readiness, risk_posture):
            if component.get("recommendations_json"):
                recommendations.extend(component["recommendations_json"])

        return {
            "snapshot_type": "compliance_readiness",
            "score": score,
            "grade": self._grade(score),
            "inputs_json": {
                "control_health": control_health["score"],
                "evidence_readiness": evidence_readiness["score"],
                "risk_posture": risk_posture["score"],
            },
            "breakdown_json": breakdown,
            "recommendations_json": recommendations or None,
        }

    def compute_governance_health(self, organization_id: uuid.UUID) -> dict:
        components = {
            "control_health": self.compute_control_health(organization_id),
            "evidence_readiness": self.compute_evidence_readiness(organization_id),
            "risk_posture": self.compute_risk_posture(organization_id),
            "task_hygiene": self.compute_task_hygiene(organization_id),
        }
        score = self._clamp_score(sum(item["score"] for item in components.values()) / len(components))
        breakdown = {
            "components": {k: v["score"] for k, v in components.items()},
            "weights": {k: 0.25 for k in components},
        }
        recommendations = []
        for item in components.values():
            if item.get("recommendations_json"):
                recommendations.extend(item["recommendations_json"])

        return {
            "snapshot_type": "governance_health",
            "score": score,
            "grade": self._grade(score),
            "inputs_json": {k: v["score"] for k, v in components.items()},
            "breakdown_json": breakdown,
            "recommendations_json": recommendations or None,
        }

    def _compute_snapshot(self, organization_id: uuid.UUID, snapshot_type: str) -> dict:
        if snapshot_type == "control_health":
            return self.compute_control_health(organization_id)
        if snapshot_type == "evidence_readiness":
            return self.compute_evidence_readiness(organization_id)
        if snapshot_type == "risk_posture":
            return self.compute_risk_posture(organization_id)
        if snapshot_type == "task_hygiene":
            return self.compute_task_hygiene(organization_id)
        if snapshot_type == "governance_health":
            return self.compute_governance_health(organization_id)
        if snapshot_type == "compliance_readiness":
            return self.compute_compliance_readiness(organization_id)
        raise ValueError("Unsupported snapshot_type")

    def materialize_snapshots(
        self,
        *,
        organization_id: uuid.UUID,
        snapshot_types: list[str] | None,
        dry_run: bool,
        created_by_user_id: uuid.UUID | None,
    ) -> list[ScoreSnapshot]:
        target_types = snapshot_types or [
            "compliance_readiness",
            "evidence_readiness",
            "control_health",
            "risk_posture",
            "task_hygiene",
            "governance_health",
        ]

        for snapshot_type in target_types:
            if snapshot_type not in SNAPSHOT_TYPES:
                raise ValueError(f"Unsupported snapshot_type: {snapshot_type}")

        calculated_at = self.now()
        result_rows: list[ScoreSnapshot] = []
        for snapshot_type in target_types:
            payload = self._compute_snapshot(organization_id, snapshot_type)
            row_kwargs = {
                "organization_id": organization_id,
                "snapshot_type": snapshot_type,
                "score": payload["score"],
                "grade": payload["grade"],
                "inputs_json": payload["inputs_json"],
                "breakdown_json": payload["breakdown_json"],
                "recommendations_json": payload["recommendations_json"],
                "calculated_at": calculated_at,
                "created_by_user_id": created_by_user_id,
            }
            if dry_run:
                row_kwargs["id"] = uuid.uuid4()
                row_kwargs["created_at"] = calculated_at
                row_kwargs["updated_at"] = calculated_at

            row = ScoreSnapshot(**row_kwargs)
            if not dry_run:
                self.db.add(row)
                self.db.flush()
            result_rows.append(row)
        return result_rows

    def latest_snapshots(self, organization_id: uuid.UUID) -> list[ScoreSnapshot]:
        rows = self.db.execute(
            select(ScoreSnapshot)
            .where(ScoreSnapshot.organization_id == organization_id)
            .order_by(ScoreSnapshot.calculated_at.desc(), ScoreSnapshot.created_at.desc())
        ).scalars().all()

        latest_by_type: dict[str, ScoreSnapshot] = {}
        for row in rows:
            if row.snapshot_type not in latest_by_type:
                latest_by_type[row.snapshot_type] = row
        return list(latest_by_type.values())

    def list_snapshots(
        self,
        organization_id: uuid.UUID,
        *,
        snapshot_type: str | None,
        limit: int,
        offset: int,
    ) -> list[ScoreSnapshot]:
        stmt = select(ScoreSnapshot).where(ScoreSnapshot.organization_id == organization_id)
        if snapshot_type:
            stmt = stmt.where(ScoreSnapshot.snapshot_type == snapshot_type)

        return list(
            self.db.execute(
                stmt.order_by(ScoreSnapshot.calculated_at.desc(), ScoreSnapshot.created_at.desc()).offset(offset).limit(limit)
            ).scalars().all()
        )

    def score_trends(
        self,
        organization_id: uuid.UUID,
        *,
        snapshot_type: str | None,
        days: int,
    ) -> dict[str, list[ScoreSnapshot]]:
        since = self.now() - timedelta(days=days)
        stmt = select(ScoreSnapshot).where(
            ScoreSnapshot.organization_id == organization_id,
            ScoreSnapshot.calculated_at >= since,
        )
        if snapshot_type:
            stmt = stmt.where(ScoreSnapshot.snapshot_type == snapshot_type)

        rows = list(
            self.db.execute(
                stmt.order_by(ScoreSnapshot.snapshot_type.asc(), ScoreSnapshot.calculated_at.asc(), ScoreSnapshot.created_at.asc())
            ).scalars().all()
        )
        out: dict[str, list[ScoreSnapshot]] = {}
        for row in rows:
            out.setdefault(row.snapshot_type, []).append(row)
        return out

    def score_delta(
        self,
        organization_id: uuid.UUID,
        *,
        snapshot_type: str,
        days: int,
    ) -> dict | None:
        since = self.now() - timedelta(days=days)
        rows = list(
            self.db.execute(
                select(ScoreSnapshot)
                .where(
                    ScoreSnapshot.organization_id == organization_id,
                    ScoreSnapshot.snapshot_type == snapshot_type,
                    ScoreSnapshot.calculated_at >= since,
                )
                .order_by(ScoreSnapshot.calculated_at.asc(), ScoreSnapshot.created_at.asc())
            ).scalars().all()
        )
        if len(rows) < 2:
            return None
        previous = rows[0]
        latest = rows[-1]
        delta = latest.score - previous.score
        direction = "unchanged"
        if delta > 0:
            direction = "improved"
        elif delta < 0:
            direction = "declined"
        return {
            "snapshot_type": snapshot_type,
            "latest_score": latest.score,
            "previous_score": previous.score,
            "delta": delta,
            "direction": direction,
            "latest_calculated_at": latest.calculated_at,
            "previous_calculated_at": previous.calculated_at,
        }

    @staticmethod
    def methodology() -> dict:
        return {
            "snapshot_types": {
                "control_health": {
                    "formula": "implemented_ratio*0.55 + latest_test_pass_ratio*0.45 - needs_review_ratio*0.2",
                    "notes": "Active controls only; archived controls excluded.",
                },
                "evidence_readiness": {
                    "formula": "verified_coverage*100 - expired_ratio*35 - needs_review_ratio*20",
                    "notes": "Uses linked evidence review and freshness metadata only.",
                },
                "risk_posture": {
                    "formula": "100 - critical_high*50 - without_owner*25 - without_controls*25 + accepted_or_mitigated*10",
                    "notes": "Operational risk hygiene score, not risk elimination claim.",
                },
                "task_hygiene": {
                    "formula": "completion*0.6 + (1-overdue_open)*0.25 + (1-urgent_open)*0.15",
                    "notes": "Measures execution hygiene from task lifecycle data.",
                },
                "compliance_readiness": {
                    "formula": "control_health*0.4 + evidence_readiness*0.4 + risk_posture*0.2",
                    "notes": "Readiness indicator only; not an audit certification score.",
                },
                "governance_health": {
                    "formula": "average(control_health, evidence_readiness, risk_posture, task_hygiene)",
                    "notes": "Aggregate governance indicator from internal system state.",
                },
            },
            "caveats": [
                "Scores are deterministic and based only on CompliVibe backend records.",
                "No external scanners, connectors, or third-party monitoring are used in this phase.",
                "Scores represent readiness/health and do not imply audit completion or legal compliance certification.",
            ],
        }
