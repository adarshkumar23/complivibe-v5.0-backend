import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.compliance.services.board_scorecard_builder import BoardScorecardBuilder
from app.compliance.services.executive_narrative_builder import ExecutiveNarrativeBuilder
from app.models.compliance_report import ComplianceReport
from app.models.compliance_report_section import ComplianceReportSection
from app.models.control import Control
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.framework import Framework
from app.models.obligation import Obligation
from app.models.organization_framework import OrganizationFramework
from app.models.organization_obligation_state import OrganizationObligationState
from app.models.risk import Risk
from app.models.risk_control_link import RiskControlLink
from app.models.score_snapshot import ScoreSnapshot
from app.models.task import Task
from app.repositories.report_repository import ReportRepository
from app.services.evidence_service import EvidenceService
from app.services.risk_service import RiskService
from app.services.scoring_service import ScoringService
from app.services.task_service import TaskService
from app.core.validation import validate_choice

ALLOWED_REPORT_TYPES = {
    "executive_summary",
    "framework_readiness",
    "evidence_readiness",
    "risk_posture",
    "task_execution",
    "control_health",
    "audit_preparation",
    "board_scorecard",
    "executive_narrative",
    "custom",
    "soc2_readiness",
    "gdpr_ropa",
    "iso27001_soa",
    "nist_ai_rmf_summary",
    "eu_ai_act_conformity",
}

REPORT_CAVEAT = (
    "This report is generated from CompliVibe system records and does not constitute legal advice, "
    "audit certification, or regulatory approval."
)


class ReportService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def validate_report_type(report_type: str) -> None:
        report_type = validate_choice(report_type, ALLOWED_REPORT_TYPES, "report_type", status_code=status.HTTP_400_BAD_REQUEST)

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _infer_section_count(row: ComplianceReport) -> int:
        sections = (row.content_json or {}).get("sections") if isinstance(row.content_json, dict) else None
        if isinstance(sections, list):
            return len(sections)
        return 0

    def validate_reporting_period(self, period_start: datetime | None, period_end: datetime | None) -> None:
        if period_start and period_end and period_end < period_start:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="period_end must be greater than or equal to period_start",
            )

    def report_context(self, row: ComplianceReport, *, section_count: int | None = None) -> dict:
        generated_at = self._as_utc(row.generated_at) or self.now()
        age_days = max(0, (self.now().date() - generated_at.date()).days)
        is_archived = row.status == "archived" or row.archived_at is not None
        is_stale = (not is_archived) and age_days > 30
        count = section_count if section_count is not None else self._infer_section_count(row)

        flags: list[str] = []
        if row.status == "generated":
            flags.append("report_generated")
        if row.status == "draft":
            flags.append("report_draft")
        if is_archived:
            flags.append("report_archived")
        if is_stale:
            flags.append("report_stale")
        if count == 0:
            flags.append("report_missing_sections")
        if not isinstance(row.provenance_json, dict) or not row.provenance_json:
            flags.append("report_missing_provenance")
        if row.inputs_summary_json is None:
            flags.append("report_missing_inputs_summary")
        if row.period_start and row.period_end and row.period_end < row.period_start:
            flags.append("invalid_period_range")
        if row.report_type == "framework_readiness" and row.framework_id is None:
            flags.append("framework_context_missing")

        return {
            "age_days": age_days,
            "section_count": count,
            "is_archived": is_archived,
            "is_stale": is_stale,
            "context_flags": flags,
        }

    def report_response_payload(self, row: ComplianceReport, *, section_count: int | None = None) -> dict:
        context = self.report_context(row, section_count=section_count)
        return {
            "id": row.id,
            "organization_id": row.organization_id,
            "report_type": row.report_type,
            "title": row.title,
            "description": row.description,
            "status": row.status,
            "framework_id": row.framework_id,
            "period_start": row.period_start,
            "period_end": row.period_end,
            "generated_by_user_id": row.generated_by_user_id,
            "generated_at": row.generated_at,
            "archived_at": row.archived_at,
            "content_json": row.content_json,
            "content_markdown": row.content_markdown,
            "provenance_json": row.provenance_json,
            "inputs_summary_json": row.inputs_summary_json,
            "age_days": context["age_days"],
            "section_count": context["section_count"],
            "is_archived": context["is_archived"],
            "is_stale": context["is_stale"],
            "context_flags": context["context_flags"],
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    def require_active_framework(self, organization_id: uuid.UUID, framework_id: uuid.UUID) -> Framework:
        framework = self.db.execute(select(Framework).where(Framework.id == framework_id)).scalar_one_or_none()
        if framework is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework not found")

        org_framework = self.db.execute(
            select(OrganizationFramework).where(
                OrganizationFramework.organization_id == organization_id,
                OrganizationFramework.framework_id == framework_id,
                OrganizationFramework.status == "active",
            )
        ).scalar_one_or_none()
        if org_framework is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Framework is not active for organization")
        return framework

    def framework_readiness_data(self, organization_id: uuid.UUID, framework_id: uuid.UUID) -> dict:
        self.require_active_framework(organization_id, framework_id)

        active_obligations = int(
            self.db.execute(
                select(func.count(Obligation.id)).where(
                    Obligation.framework_id == framework_id,
                    Obligation.status == "active",
                )
            ).scalar_one()
        )

        applicable_obligations = int(
            self.db.execute(
                select(func.count(OrganizationObligationState.id))
                .join(Obligation, Obligation.id == OrganizationObligationState.obligation_id)
                .where(
                    OrganizationObligationState.organization_id == organization_id,
                    Obligation.framework_id == framework_id,
                    OrganizationObligationState.applicability_status == "applicable",
                )
            ).scalar_one()
        )

        obligations_with_controls = int(
            self.db.execute(
                select(func.count(func.distinct(ControlObligationMapping.obligation_id)))
                .join(Obligation, Obligation.id == ControlObligationMapping.obligation_id)
                .where(
                    ControlObligationMapping.organization_id == organization_id,
                    ControlObligationMapping.status == "active",
                    Obligation.framework_id == framework_id,
                )
            ).scalar_one()
        )

        obligation_baseline = applicable_obligations if applicable_obligations > 0 else active_obligations
        obligations_without_controls = max(0, obligation_baseline - obligations_with_controls)

        mapped_control_ids = self.db.execute(
            select(func.distinct(ControlObligationMapping.control_id))
            .join(Obligation, Obligation.id == ControlObligationMapping.obligation_id)
            .where(
                ControlObligationMapping.organization_id == organization_id,
                ControlObligationMapping.status == "active",
                Obligation.framework_id == framework_id,
            )
        ).scalars().all()

        if mapped_control_ids:
            controls_total = int(
                self.db.execute(
                    select(func.count(Control.id)).where(
                        Control.organization_id == organization_id,
                        Control.id.in_(mapped_control_ids),
                        Control.status != "archived",
                    )
                ).scalar_one()
            )
            controls_implemented = int(
                self.db.execute(
                    select(func.count(Control.id)).where(
                        Control.organization_id == organization_id,
                        Control.id.in_(mapped_control_ids),
                        Control.status == "implemented",
                    )
                ).scalar_one()
            )

            controls_with_verified_evidence = int(
                self.db.execute(
                    select(func.count(func.distinct(EvidenceControlLink.control_id)))
                    .join(EvidenceItem, EvidenceItem.id == EvidenceControlLink.evidence_item_id)
                    .where(
                        EvidenceControlLink.organization_id == organization_id,
                        EvidenceControlLink.control_id.in_(mapped_control_ids),
                        EvidenceControlLink.link_status == "active",
                        EvidenceItem.organization_id == organization_id,
                        EvidenceItem.status == "active",
                        EvidenceItem.review_status == "verified",
                        EvidenceItem.freshness_status.in_(["current", "expiring_soon"]),
                    )
                ).scalar_one()
            )

            risks_linked = int(
                self.db.execute(
                    select(func.count(func.distinct(RiskControlLink.risk_id)))
                    .join(Risk, Risk.id == RiskControlLink.risk_id)
                    .where(
                        RiskControlLink.organization_id == organization_id,
                        RiskControlLink.control_id.in_(mapped_control_ids),
                        RiskControlLink.status == "active",
                        Risk.organization_id == organization_id,
                        Risk.status != "archived",
                    )
                ).scalar_one()
            )

            open_tasks = int(
                self.db.execute(
                    select(func.count(Task.id)).where(
                        Task.organization_id == organization_id,
                        Task.status.in_(["open", "in_progress", "blocked"]),
                        (
                            (Task.linked_entity_type == "control") & (Task.linked_entity_id.in_(mapped_control_ids))
                        )
                        | (
                            (Task.linked_entity_type == "obligation")
                            & (
                                Task.linked_entity_id.in_(
                                    select(Obligation.id).where(Obligation.framework_id == framework_id)
                                )
                            )
                        )
                        | ((Task.linked_entity_type == "framework") & (Task.linked_entity_id == framework_id)),
                    )
                ).scalar_one()
            )
        else:
            controls_total = 0
            controls_implemented = 0
            controls_with_verified_evidence = 0
            risks_linked = 0
            open_tasks = 0

        latest_scores = ScoringService(self.db).latest_snapshots(organization_id)
        latest_score_snapshots = [
            {
                "id": str(row.id),
                "snapshot_type": row.snapshot_type,
                "score": row.score,
                "grade": row.grade,
                "calculated_at": row.calculated_at.isoformat(),
            }
            for row in latest_scores
        ]

        return {
            "framework_id": framework_id,
            "active_obligations": active_obligations,
            "applicable_obligations": applicable_obligations,
            "obligations_with_controls": obligations_with_controls,
            "obligations_without_controls": obligations_without_controls,
            "controls_total": controls_total,
            "controls_implemented": controls_implemented,
            "controls_with_verified_evidence": controls_with_verified_evidence,
            "risks_linked": risks_linked,
            "open_tasks": open_tasks,
            "latest_score_snapshots": latest_score_snapshots,
        }

    def _section(self, *, key: str, title: str, body: str, data: dict, provenance: dict, sort_order: int) -> dict:
        return {
            "section_key": key,
            "title": title,
            "body_markdown": body,
            "data_json": data,
            "provenance_json": provenance,
            "sort_order": sort_order,
        }

    def _build_executive_summary(self, organization_id: uuid.UUID) -> tuple[list[dict], dict, dict]:
        control_count = int(
            self.db.execute(
                select(func.count(Control.id)).where(
                    Control.organization_id == organization_id,
                    Control.status != "archived",
                )
            ).scalar_one()
        )
        active_frameworks = int(
            self.db.execute(
                select(func.count(OrganizationFramework.id)).where(
                    OrganizationFramework.organization_id == organization_id,
                    OrganizationFramework.status == "active",
                )
            ).scalar_one()
        )
        evidence_summary = EvidenceService(self.db).readiness_summary(organization_id)
        risk_summary = RiskService(self.db).summary(organization_id)
        task_summary = TaskService(self.db).summary(organization_id)
        latest_scores = ScoringService(self.db).latest_snapshots(organization_id)

        top_risks = self.db.execute(
            select(Risk)
            .where(Risk.organization_id == organization_id, Risk.status != "archived")
            .order_by(
                case((Risk.severity == "critical", 4), (Risk.severity == "high", 3), (Risk.severity == "medium", 2), else_=1).desc(),
                Risk.inherent_score.desc(),
                Risk.created_at.desc(),
            )
            .limit(5)
        ).scalars().all()

        sections = [
            self._section(
                key="overview",
                title="Overview",
                body=(
                    "This report summarizes current readiness signals based on records stored in CompliVibe.\n\n"
                    f"- Active frameworks: {active_frameworks}\n"
                    f"- Active controls: {control_count}\n"
                    f"- Verified evidence items: {evidence_summary['verified_evidence_items']}"
                ),
                data={
                    "active_frameworks": active_frameworks,
                    "active_controls": control_count,
                    "verified_evidence_items": evidence_summary["verified_evidence_items"],
                },
                provenance={"source_models": ["organization_frameworks", "controls", "evidence_items"]},
                sort_order=1,
            ),
            self._section(
                key="score_snapshot",
                title="Score Snapshot",
                body=(
                    "Latest materialized readiness/health snapshots:\n\n"
                    + "\n".join(
                        [f"- {s.snapshot_type}: {s.score} ({s.grade})" for s in latest_scores]
                        or ["- No score snapshots available."]
                    )
                ),
                data={
                    "snapshots": [
                        {
                            "id": str(s.id),
                            "snapshot_type": s.snapshot_type,
                            "score": s.score,
                            "grade": s.grade,
                            "calculated_at": s.calculated_at.isoformat(),
                        }
                        for s in latest_scores
                    ]
                },
                provenance={"source_models": ["score_snapshots"], "source_ids": [str(s.id) for s in latest_scores]},
                sort_order=2,
            ),
            self._section(
                key="top_risks",
                title="Top Risks",
                body=(
                    "Current highest-priority risks by severity and inherent score:\n\n"
                    + "\n".join(
                        [f"- {r.title} ({r.severity}, score {r.inherent_score})" for r in top_risks]
                        or ["- No active risks."]
                    )
                ),
                data={
                    "top_risks": [
                        {"id": str(r.id), "title": r.title, "severity": r.severity, "inherent_score": r.inherent_score}
                        for r in top_risks
                    ]
                },
                provenance={"source_models": ["risks"], "source_ids": [str(r.id) for r in top_risks]},
                sort_order=3,
            ),
            self._section(
                key="open_tasks",
                title="Open Tasks",
                body=(
                    f"Open tasks: {task_summary['open_tasks']}\n"
                    f"Overdue tasks: {task_summary['overdue_tasks']}\n"
                    f"Urgent open tasks: {task_summary['urgent_open_tasks']}"
                ),
                data=task_summary,
                provenance={"source_models": ["tasks"]},
                sort_order=4,
            ),
            self._section(
                key="evidence_status",
                title="Evidence Status",
                body=(
                    f"Evidence needing review: {evidence_summary['needs_review_evidence_items']}\n"
                    f"Expired evidence items: {evidence_summary['expired_evidence_items']}\n"
                    f"Controls without evidence: {evidence_summary['controls_without_evidence']}"
                ),
                data=evidence_summary,
                provenance={"source_models": ["evidence_items", "evidence_control_links", "controls"]},
                sort_order=5,
            ),
            self._section(
                key="caveats",
                title="Caveats",
                body=REPORT_CAVEAT,
                data={"caveat": REPORT_CAVEAT},
                provenance={"source_models": []},
                sort_order=99,
            ),
        ]

        inputs_summary = {
            "active_frameworks": active_frameworks,
            "active_controls": control_count,
            "top_risk_count": len(top_risks),
            "score_snapshot_count": len(latest_scores),
        }
        provenance = {
            "generated_at": self.now().isoformat(),
            "source_model_counts": {
                "score_snapshots": len(latest_scores),
                "risks": len(top_risks),
                "tasks": task_summary["total_tasks"],
                "evidence_items": evidence_summary["total_evidence_items"],
            },
            "score_snapshot_ids": [str(s.id) for s in latest_scores],
        }
        return sections, inputs_summary, provenance

    def _build_framework_readiness(self, organization_id: uuid.UUID, framework_id: uuid.UUID) -> tuple[list[dict], dict, dict]:
        framework = self.require_active_framework(organization_id, framework_id)
        readiness = self.framework_readiness_data(organization_id, framework_id)

        sections = [
            self._section(
                key="framework_scope",
                title="Framework Scope",
                body=(
                    f"Framework: {framework.name} ({framework.code})\n"
                    f"Coverage level: {framework.coverage_level}\n"
                    f"Status: {framework.status}"
                ),
                data={
                    "framework_id": str(framework.id),
                    "code": framework.code,
                    "name": framework.name,
                    "coverage_level": framework.coverage_level,
                    "status": framework.status,
                },
                provenance={"source_models": ["frameworks", "organization_frameworks"], "source_ids": [str(framework.id)]},
                sort_order=1,
            ),
            self._section(
                key="obligation_status",
                title="Obligation Status",
                body=(
                    f"Active obligations: {readiness['active_obligations']}\n"
                    f"Applicable obligations: {readiness['applicable_obligations']}\n"
                    f"Obligations with controls: {readiness['obligations_with_controls']}\n"
                    f"Obligations without controls: {readiness['obligations_without_controls']}"
                ),
                data={k: readiness[k] for k in ["active_obligations", "applicable_obligations", "obligations_with_controls", "obligations_without_controls"]},
                provenance={"source_models": ["obligations", "organization_obligation_states", "control_obligation_mappings"]},
                sort_order=2,
            ),
            self._section(
                key="control_status",
                title="Control Status",
                body=(
                    f"Mapped controls: {readiness['controls_total']}\n"
                    f"Implemented controls: {readiness['controls_implemented']}"
                ),
                data={k: readiness[k] for k in ["controls_total", "controls_implemented"]},
                provenance={"source_models": ["controls", "control_obligation_mappings"]},
                sort_order=3,
            ),
            self._section(
                key="evidence_status",
                title="Evidence Status",
                body=(
                    f"Controls with verified evidence: {readiness['controls_with_verified_evidence']}\n"
                    f"Open linked tasks: {readiness['open_tasks']}"
                ),
                data={k: readiness[k] for k in ["controls_with_verified_evidence", "open_tasks"]},
                provenance={"source_models": ["evidence_items", "evidence_control_links", "tasks"]},
                sort_order=4,
            ),
            self._section(
                key="gaps_and_next_actions",
                title="Gaps and Next Actions",
                body=(
                    f"Outstanding obligation gaps: {readiness['obligations_without_controls']}\n"
                    f"Linked risks: {readiness['risks_linked']}\n"
                    "Prioritize unresolved mappings, evidence refresh, and open tasks for this framework."
                ),
                data={"obligations_without_controls": readiness["obligations_without_controls"], "risks_linked": readiness["risks_linked"]},
                provenance={"source_models": ["control_obligation_mappings", "risk_control_links", "risks", "tasks"]},
                sort_order=5,
            ),
            self._section(
                key="caveats",
                title="Caveats",
                body=REPORT_CAVEAT,
                data={"caveat": REPORT_CAVEAT},
                provenance={"source_models": []},
                sort_order=99,
            ),
        ]
        inputs_summary = readiness
        provenance = {
            "generated_at": self.now().isoformat(),
            "framework_id": str(framework_id),
            "source_model_counts": {
                "obligations": readiness["active_obligations"],
                "controls": readiness["controls_total"],
                "score_snapshots": len(readiness["latest_score_snapshots"]),
            },
            "score_snapshot_ids": [s["id"] for s in readiness["latest_score_snapshots"]],
        }
        return sections, inputs_summary, provenance

    def _build_evidence_readiness(self, organization_id: uuid.UUID) -> tuple[list[dict], dict, dict]:
        summary = EvidenceService(self.db).readiness_summary(organization_id)
        expired_rows = self.db.execute(
            select(EvidenceItem)
            .where(
                EvidenceItem.organization_id == organization_id,
                EvidenceItem.status == "active",
                EvidenceItem.freshness_status == "expired",
            )
            .order_by(EvidenceItem.updated_at.desc())
            .limit(10)
        ).scalars().all()
        needs_review_rows = self.db.execute(
            select(EvidenceItem)
            .where(
                EvidenceItem.organization_id == organization_id,
                EvidenceItem.status == "active",
                EvidenceItem.review_status.in_(["not_reviewed", "needs_review"]),
            )
            .order_by(EvidenceItem.updated_at.desc())
            .limit(10)
        ).scalars().all()

        sections = [
            self._section(
                key="evidence_status",
                title="Evidence Status",
                body=(
                    f"Total active evidence: {summary['total_evidence_items']}\n"
                    f"Verified evidence: {summary['verified_evidence_items']}\n"
                    f"Evidence needing review: {summary['needs_review_evidence_items']}"
                ),
                data=summary,
                provenance={"source_models": ["evidence_items", "evidence_control_links", "controls"]},
                sort_order=1,
            ),
            self._section(
                key="expired_evidence",
                title="Expired Evidence",
                body=(
                    "Expired evidence items (sample):\n\n"
                    + "\n".join([f"- {e.title}" for e in expired_rows] or ["- None"]) 
                ),
                data={"count": summary["expired_evidence_items"], "items": [{"id": str(e.id), "title": e.title} for e in expired_rows]},
                provenance={"source_models": ["evidence_items"], "source_ids": [str(e.id) for e in expired_rows]},
                sort_order=2,
            ),
            self._section(
                key="evidence_needing_review",
                title="Evidence Needing Review",
                body=(
                    "Evidence requiring review (sample):\n\n"
                    + "\n".join([f"- {e.title}" for e in needs_review_rows] or ["- None"]) 
                ),
                data={"count": summary["needs_review_evidence_items"], "items": [{"id": str(e.id), "title": e.title} for e in needs_review_rows]},
                provenance={"source_models": ["evidence_items"], "source_ids": [str(e.id) for e in needs_review_rows]},
                sort_order=3,
            ),
            self._section(
                key="controls_without_evidence",
                title="Controls Without Evidence",
                body=f"Controls without evidence: {summary['controls_without_evidence']}",
                data={"controls_without_evidence": summary["controls_without_evidence"]},
                provenance={"source_models": ["controls", "evidence_control_links"]},
                sort_order=4,
            ),
            self._section(
                key="caveats",
                title="Caveats",
                body=REPORT_CAVEAT,
                data={"caveat": REPORT_CAVEAT},
                provenance={"source_models": []},
                sort_order=99,
            ),
        ]

        provenance = {
            "generated_at": self.now().isoformat(),
            "source_model_counts": {
                "evidence_items": summary["total_evidence_items"],
                "controls_without_evidence": summary["controls_without_evidence"],
            },
            "source_ids": [str(e.id) for e in expired_rows + needs_review_rows],
        }
        return sections, summary, provenance

    def _build_risk_posture(self, organization_id: uuid.UUID) -> tuple[list[dict], dict, dict]:
        summary = RiskService(self.db).summary(organization_id)
        critical_high = self.db.execute(
            select(Risk)
            .where(
                Risk.organization_id == organization_id,
                Risk.status != "archived",
                Risk.severity.in_(["critical", "high"]),
            )
            .order_by(Risk.inherent_score.desc(), Risk.updated_at.desc())
            .limit(10)
        ).scalars().all()

        sections = [
            self._section(
                key="risk_status",
                title="Risk Status",
                body=(
                    f"Total risks: {summary['total_risks']}\n"
                    f"Open risks: {summary['open_risks']}\n"
                    f"Accepted risks: {summary['accepted_risks']}\n"
                    f"Mitigated risks: {summary['mitigated_risks']}"
                ),
                data=summary,
                provenance={"source_models": ["risks", "risk_control_links"]},
                sort_order=1,
            ),
            self._section(
                key="critical_high_risks",
                title="Critical/High Risks",
                body=(
                    "Critical/high risks (sample):\n\n"
                    + "\n".join([f"- {r.title} ({r.severity})" for r in critical_high] or ["- None"]) 
                ),
                data={
                    "critical_risks": summary["critical_risks"],
                    "high_risks": summary["high_risks"],
                    "items": [{"id": str(r.id), "title": r.title, "severity": r.severity} for r in critical_high],
                },
                provenance={"source_models": ["risks"], "source_ids": [str(r.id) for r in critical_high]},
                sort_order=2,
            ),
            self._section(
                key="risks_without_controls",
                title="Risks Without Controls",
                body=f"Risks without controls: {summary['risks_without_controls']}",
                data={"risks_without_controls": summary["risks_without_controls"]},
                provenance={"source_models": ["risks", "risk_control_links"]},
                sort_order=3,
            ),
            self._section(
                key="accepted_risks",
                title="Accepted Risks",
                body=f"Accepted risks: {summary['accepted_risks']}",
                data={"accepted_risks": summary["accepted_risks"]},
                provenance={"source_models": ["risks"]},
                sort_order=4,
            ),
            self._section(
                key="caveats",
                title="Caveats",
                body=REPORT_CAVEAT,
                data={"caveat": REPORT_CAVEAT},
                provenance={"source_models": []},
                sort_order=99,
            ),
        ]
        provenance = {
            "generated_at": self.now().isoformat(),
            "source_model_counts": {
                "risks": summary["total_risks"],
                "critical_high_sample": len(critical_high),
            },
            "source_ids": [str(r.id) for r in critical_high],
        }
        return sections, summary, provenance

    def _build_task_execution(self, organization_id: uuid.UUID) -> tuple[list[dict], dict, dict]:
        summary = TaskService(self.db).summary(organization_id)

        overdue_rows = self.db.execute(
            select(Task)
            .where(
                Task.organization_id == organization_id,
                Task.status.in_(["open", "in_progress", "blocked"]),
                Task.due_date.is_not(None),
                Task.due_date < self.now(),
            )
            .order_by(Task.due_date.asc())
            .limit(10)
        ).scalars().all()

        sections = [
            self._section(
                key="task_status",
                title="Task Status",
                body=(
                    f"Total tasks: {summary['total_tasks']}\n"
                    f"Open tasks: {summary['open_tasks']}\n"
                    f"Completed tasks: {summary['completed_tasks']}"
                ),
                data=summary,
                provenance={"source_models": ["tasks"]},
                sort_order=1,
            ),
            self._section(
                key="overdue_tasks",
                title="Overdue Tasks",
                body=(
                    f"Overdue tasks: {summary['overdue_tasks']}\n\n"
                    + "\n".join([f"- {t.title}" for t in overdue_rows] or ["- None"]) 
                ),
                data={"overdue_tasks": summary["overdue_tasks"], "items": [{"id": str(t.id), "title": t.title} for t in overdue_rows]},
                provenance={"source_models": ["tasks"], "source_ids": [str(t.id) for t in overdue_rows]},
                sort_order=2,
            ),
            self._section(
                key="urgent_open_tasks",
                title="Urgent Open Tasks",
                body=f"Urgent open tasks: {summary['urgent_open_tasks']}",
                data={"urgent_open_tasks": summary["urgent_open_tasks"]},
                provenance={"source_models": ["tasks"]},
                sort_order=3,
            ),
            self._section(
                key="completed_tasks",
                title="Completed Tasks",
                body=f"Completed tasks: {summary['completed_tasks']}",
                data={"completed_tasks": summary["completed_tasks"]},
                provenance={"source_models": ["tasks"]},
                sort_order=4,
            ),
            self._section(
                key="caveats",
                title="Caveats",
                body=REPORT_CAVEAT,
                data={"caveat": REPORT_CAVEAT},
                provenance={"source_models": []},
                sort_order=99,
            ),
        ]
        provenance = {
            "generated_at": self.now().isoformat(),
            "source_model_counts": {"tasks": summary["total_tasks"], "overdue_sample": len(overdue_rows)},
            "source_ids": [str(t.id) for t in overdue_rows],
        }
        return sections, summary, provenance

    def _build_board_scorecard(self, organization_id: uuid.UUID) -> tuple[list[dict], dict, dict]:
        payload = BoardScorecardBuilder().build(organization_id, self.db)
        sections = [
            self._section(
                key="board_scorecard",
                title="Board Scorecard",
                body=payload["narrative"],
                data=payload,
                provenance={
                    "source_models": [
                        "score_snapshots",
                        "risks",
                        "issues",
                        "compliance_certifications",
                        "compliance_deadlines",
                        "organization_obligation_states",
                    ]
                },
                sort_order=1,
            ),
            self._section(
                key="caveats",
                title="Caveats",
                body=REPORT_CAVEAT,
                data={"caveat": REPORT_CAVEAT},
                provenance={"source_models": []},
                sort_order=99,
            ),
        ]
        provenance = {
            "generated_at": self.now().isoformat(),
            "source_model_counts": {
                "risks_summary": len(payload["risks_summary"]),
                "upcoming_deadlines": len(payload["upcoming_deadlines"]),
            },
        }
        return sections, payload, provenance

    def _build_executive_narrative(self, organization_id: uuid.UUID) -> tuple[list[dict], dict, dict]:
        payload = ExecutiveNarrativeBuilder().build(organization_id, self.db)
        section_text = payload["sections"]
        sections = [
            self._section(
                key="where_we_stand",
                title="Where We Stand",
                body=section_text["where_we_stand"],
                data={"where_we_stand": section_text["where_we_stand"]},
                provenance={"source_models": ["score_snapshots", "frameworks", "controls", "control_obligation_mappings", "obligations"]},
                sort_order=1,
            ),
            self._section(
                key="needs_attention",
                title="Needs Attention",
                body=section_text["needs_attention"],
                data={"needs_attention": section_text["needs_attention"]},
                provenance={"source_models": ["risks", "issues"]},
                sort_order=2,
            ),
            self._section(
                key="achievements_this_quarter",
                title="Achievements This Quarter",
                body=section_text["achievements_this_quarter"],
                data={"achievements_this_quarter": section_text["achievements_this_quarter"]},
                provenance={"source_models": ["compliance_certifications", "risks"]},
                sort_order=3,
            ),
            self._section(
                key="upcoming",
                title="Upcoming",
                body=section_text["upcoming"],
                data={"upcoming": section_text["upcoming"]},
                provenance={"source_models": ["compliance_deadlines"]},
                sort_order=4,
            ),
            self._section(
                key="caveats",
                title="Caveats",
                body=payload["caveat"],
                data={"caveat": payload["caveat"]},
                provenance={"source_models": []},
                sort_order=99,
            ),
        ]
        provenance = {
            "generated_at": self.now().isoformat(),
            "source_model_counts": {
                "sections": len(section_text),
            },
        }
        return sections, payload, provenance

    def build_report(
        self,
        *,
        organization_id: uuid.UUID,
        report_type: str,
        framework_id: uuid.UUID | None,
    ) -> tuple[list[dict], dict, dict]:
        self.validate_report_type(report_type)

        if report_type == "executive_summary":
            return self._build_executive_summary(organization_id)
        if report_type == "framework_readiness":
            if framework_id is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="framework_id is required for framework_readiness")
            return self._build_framework_readiness(organization_id, framework_id)
        if report_type == "evidence_readiness":
            return self._build_evidence_readiness(organization_id)
        if report_type == "risk_posture":
            return self._build_risk_posture(organization_id)
        if report_type == "task_execution":
            return self._build_task_execution(organization_id)
        if report_type == "control_health":
            # Control health is represented via latest score snapshot + control counts.
            return self._build_executive_summary(organization_id)
        if report_type == "audit_preparation":
            return self._build_executive_summary(organization_id)
        if report_type == "board_scorecard":
            return self._build_board_scorecard(organization_id)
        if report_type == "executive_narrative":
            return self._build_executive_narrative(organization_id)

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported report_type")

    def persist_report(
        self,
        *,
        organization_id: uuid.UUID,
        report_type: str,
        title: str,
        description: str | None,
        framework_id: uuid.UUID | None,
        period_start: datetime | None,
        period_end: datetime | None,
        generated_by_user_id: uuid.UUID,
        sections: list[dict],
        inputs_summary: dict,
        provenance: dict,
    ) -> tuple[ComplianceReport, list[ComplianceReportSection]]:
        now = self.now()
        content_json = {"sections": [{"section_key": s["section_key"], "title": s["title"]} for s in sections]}
        content_markdown = "\n\n".join([f"## {s['title']}\n{s['body_markdown']}" for s in sections])

        report = ComplianceReport(
            organization_id=organization_id,
            report_type=report_type,
            title=title,
            description=description,
            status="generated",
            framework_id=framework_id,
            period_start=period_start,
            period_end=period_end,
            generated_by_user_id=generated_by_user_id,
            generated_at=now,
            content_json=content_json,
            content_markdown=content_markdown,
            provenance_json=provenance,
            inputs_summary_json=inputs_summary,
        )
        self.db.add(report)
        self.db.flush()

        section_rows: list[ComplianceReportSection] = []
        for s in sections:
            section_row = ComplianceReportSection(
                organization_id=organization_id,
                report_id=report.id,
                section_key=s["section_key"],
                title=s["title"],
                body_markdown=s["body_markdown"],
                data_json=s["data_json"],
                provenance_json=s["provenance_json"],
                sort_order=s["sort_order"],
                created_at=now,
            )
            self.db.add(section_row)
            self.db.flush()
            section_rows.append(section_row)

        return report, section_rows

    def build_dry_run_report(
        self,
        *,
        organization_id: uuid.UUID,
        report_type: str,
        title: str,
        description: str | None,
        framework_id: uuid.UUID | None,
        period_start: datetime | None,
        period_end: datetime | None,
        generated_by_user_id: uuid.UUID,
        sections: list[dict],
        inputs_summary: dict,
        provenance: dict,
    ) -> tuple[ComplianceReport, list[ComplianceReportSection]]:
        now = self.now()
        report = ComplianceReport(
            id=uuid.uuid4(),
            organization_id=organization_id,
            report_type=report_type,
            title=title,
            description=description,
            status="draft",
            framework_id=framework_id,
            period_start=period_start,
            period_end=period_end,
            generated_by_user_id=generated_by_user_id,
            generated_at=now,
            archived_at=None,
            content_json={"sections": [{"section_key": s["section_key"], "title": s["title"]} for s in sections]},
            content_markdown="\n\n".join([f"## {s['title']}\n{s['body_markdown']}" for s in sections]),
            provenance_json=provenance,
            inputs_summary_json=inputs_summary,
            created_at=now,
            updated_at=now,
        )

        section_rows: list[ComplianceReportSection] = []
        for s in sections:
            section_rows.append(
                ComplianceReportSection(
                    id=uuid.uuid4(),
                    organization_id=organization_id,
                    report_id=report.id,
                    section_key=s["section_key"],
                    title=s["title"],
                    body_markdown=s["body_markdown"],
                    data_json=s["data_json"],
                    provenance_json=s["provenance_json"],
                    sort_order=s["sort_order"],
                    created_at=now,
                )
            )

        return report, section_rows

    def summary(self, organization_id: uuid.UUID) -> dict:
        now = self.now()
        since_30d = now - timedelta(days=30)

        total_reports = int(
            self.db.execute(select(func.count(ComplianceReport.id)).where(ComplianceReport.organization_id == organization_id)).scalar_one()
        )
        generated_reports = int(
            self.db.execute(
                select(func.count(ComplianceReport.id)).where(
                    ComplianceReport.organization_id == organization_id,
                    ComplianceReport.status == "generated",
                )
            ).scalar_one()
        )
        archived_reports = int(
            self.db.execute(
                select(func.count(ComplianceReport.id)).where(
                    ComplianceReport.organization_id == organization_id,
                    ComplianceReport.status == "archived",
                )
            ).scalar_one()
        )
        reports_last_30d = int(
            self.db.execute(
                select(func.count(ComplianceReport.id)).where(
                    ComplianceReport.organization_id == organization_id,
                    ComplianceReport.generated_at >= since_30d,
                )
            ).scalar_one()
        )
        stale_reports_30d = int(
            self.db.execute(
                select(func.count(ComplianceReport.id)).where(
                    ComplianceReport.organization_id == organization_id,
                    ComplianceReport.status == "generated",
                    ComplianceReport.generated_at < since_30d,
                )
            ).scalar_one()
        )

        latest_executive_summary_at = self.db.execute(
            select(func.max(ComplianceReport.generated_at)).where(
                ComplianceReport.organization_id == organization_id,
                ComplianceReport.report_type == "executive_summary",
            )
        ).scalar_one()

        latest_framework_readiness_at = self.db.execute(
            select(func.max(ComplianceReport.generated_at)).where(
                ComplianceReport.organization_id == organization_id,
                ComplianceReport.report_type == "framework_readiness",
            )
        ).scalar_one()

        latest_risk_posture_at = self.db.execute(
            select(func.max(ComplianceReport.generated_at)).where(
                ComplianceReport.organization_id == organization_id,
                ComplianceReport.report_type == "risk_posture",
            )
        ).scalar_one()

        archived_ratio = round((archived_reports / total_reports), 4) if total_reports else 0.0
        context_flags: list[str] = []
        if total_reports == 0:
            context_flags.append("no_reports_available")
        if reports_last_30d == 0 and total_reports > 0:
            context_flags.append("no_recent_reports")
        if stale_reports_30d > 0:
            context_flags.append("stale_generated_reports_present")
        if total_reports > 0 and archived_reports == total_reports:
            context_flags.append("all_reports_archived")
        if total_reports > 0 and generated_reports == 0:
            context_flags.append("no_active_generated_reports")

        return {
            "total_reports": total_reports,
            "generated_reports": generated_reports,
            "archived_reports": archived_reports,
            "reports_last_30d": reports_last_30d,
            "stale_reports_30d": stale_reports_30d,
            "archived_ratio": archived_ratio,
            "context_flags": context_flags,
            "latest_executive_summary_at": latest_executive_summary_at,
            "latest_framework_readiness_at": latest_framework_readiness_at,
            "latest_risk_posture_at": latest_risk_posture_at,
        }

    def report_or_404(self, organization_id: uuid.UUID, report_id: uuid.UUID) -> ComplianceReport:
        row = ReportRepository(self.db).get_report(report_id)
        if row is None or row.organization_id != organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
        return row
