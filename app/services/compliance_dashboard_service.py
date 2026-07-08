import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.audit_finding import AuditFinding
from app.models.compliance_deadline import ComplianceDeadline
from app.models.compliance_policy import CompliancePolicy
from app.models.control import Control
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.common_control_mapping import CommonControlMapping
from app.models.control_monitoring_definition import ControlMonitoringDefinition
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.control_test_definition import ControlTestDefinition
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.framework import Framework
from app.models.obligation import Obligation
from app.models.organization_framework import OrganizationFramework
from app.models.organization_obligation_state import OrganizationObligationState
from app.models.score_snapshot import ScoreSnapshot
from app.models.task import Task
from app.models.vendor_assessment import VendorAssessment
from app.schemas.audit_log import AuditLogRead
from app.services.compliance_policy_service import CompliancePolicyService
from app.services.control_monitoring_alert_service import ControlMonitoringAlertService
from app.services.control_monitoring_service import ControlMonitoringService
from app.services.evidence_service import EvidenceService
from app.services.risk_service import RiskService
from app.services.task_service import TaskService
from app.services.vendor_service import VendorService


class ComplianceDashboardService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def utcdate() -> date:
        return datetime.now(UTC).date()

    def _active_framework_rows(self, organization_id: uuid.UUID) -> list[tuple[OrganizationFramework, Framework]]:
        stmt = (
            select(OrganizationFramework, Framework)
            .join(Framework, Framework.id == OrganizationFramework.framework_id)
            .where(
                OrganizationFramework.organization_id == organization_id,
                OrganizationFramework.status == "active",
            )
            .order_by(Framework.name.asc())
        )
        return self.db.execute(stmt).all()

    def framework_control_coverage_pct(self, organization_id: uuid.UUID, framework_id: uuid.UUID) -> float:
        """Public entry point for other services (e.g. the trust center) that need the
        same real control-coverage number shown in posture-summary / framework-readiness,
        rather than reimplementing their own (drifting) coverage query."""
        return float(self._framework_counts(organization_id, framework_id)["control_coverage_pct"])

    def _mapped_control_obligation_pairs(self, organization_id: uuid.UUID, framework_id: uuid.UUID) -> set[tuple[uuid.UUID, uuid.UUID]]:
        """Real (control_id, obligation_id) pairs mapped for this framework, unioned
        across BOTH control-linking mechanisms in this codebase: the direct
        ControlObligationMapping (used by most of the app) and CommonControlMapping
        (the "common controls" reuse-across-frameworks feature). These are two
        historically disconnected data models for the same underlying concept -- a
        control mapped to an obligation ONLY via CommonControlMapping was previously
        invisible here, silently under-counting real coverage (see G9 item 18).
        Mirrors the union pattern already used correctly in oscal_export_service.py.
        """
        direct_pairs = set(
            self.db.execute(
                select(ControlObligationMapping.control_id, ControlObligationMapping.obligation_id)
                .join(Obligation, Obligation.id == ControlObligationMapping.obligation_id)
                .where(
                    ControlObligationMapping.organization_id == organization_id,
                    ControlObligationMapping.status == "active",
                    Obligation.framework_id == framework_id,
                    Obligation.status == "active",
                )
            ).all()
        )
        common_pairs = set(
            self.db.execute(
                select(CommonControlMapping.control_id, CommonControlMapping.obligation_id)
                .join(Obligation, Obligation.id == CommonControlMapping.obligation_id)
                .where(
                    CommonControlMapping.organization_id == organization_id,
                    CommonControlMapping.status == "active",
                    CommonControlMapping.framework_id == framework_id,
                    Obligation.status == "active",
                )
            ).all()
        )
        return direct_pairs | common_pairs

    def _framework_counts(self, organization_id: uuid.UUID, framework_id: uuid.UUID) -> dict[str, int | float]:
        obligation_count = int(
            self.db.execute(
                select(func.count(Obligation.id)).where(
                    Obligation.framework_id == framework_id,
                    Obligation.status == "active",
                )
            ).scalar_one()
        )

        mapped_pairs = self._mapped_control_obligation_pairs(organization_id, framework_id)
        mapped_control_ids = {control_id for control_id, _ in mapped_pairs}
        mapped_obligation_ids = {obligation_id for _, obligation_id in mapped_pairs}
        mapped_control_count = len(mapped_control_ids)
        mapped_obligation_count = len(mapped_obligation_ids)

        verified_mapped_controls = int(
            self.db.execute(
                select(func.count(func.distinct(EvidenceControlLink.control_id))).where(
                    EvidenceControlLink.organization_id == organization_id,
                    EvidenceControlLink.link_status == "active",
                    EvidenceControlLink.control_id.in_(mapped_control_ids),
                    EvidenceControlLink.evidence_item_id.in_(
                        select(EvidenceItem.id).where(
                            EvidenceItem.organization_id == organization_id,
                            EvidenceItem.status != "archived",
                            EvidenceItem.review_status == "verified",
                        )
                    ),
                )
            ).scalar_one()
        ) if mapped_control_ids else 0

        control_coverage_pct = round((mapped_obligation_count / obligation_count) * 100, 2) if obligation_count else 0.0
        evidence_verified_pct = round((verified_mapped_controls / mapped_control_count) * 100, 2) if mapped_control_count else 0.0

        return {
            "obligation_count": obligation_count,
            "mapped_control_count": mapped_control_count,
            "mapped_obligation_count": mapped_obligation_count,
            "control_coverage_pct": control_coverage_pct,
            "evidence_verified_pct": evidence_verified_pct,
            "open_gaps_count": max(0, obligation_count - mapped_obligation_count),
        }

    # A score snapshot older than this is considered stale for dashboard display purposes,
    # regardless of whether the underlying data has changed since -- the number itself is
    # simply too old to present as "current" without a caveat.
    SCORE_SNAPSHOT_STALE_AFTER_HOURS = 24

    # Audit log action prefixes that indicate data feeding into the compliance score may
    # have changed since a snapshot was calculated (mirrors the recent_activity() scope).
    _SCORE_RELEVANT_ACTION_PREFIXES = (
        "control.",
        "evidence.",
        "control_obligation_mapping.",
        "obligation.",
        "risk.",
        "compliance_policy.",
        "vendor_assessment.",
    )

    def _underlying_data_changed_since(self, organization_id: uuid.UUID, since: datetime) -> bool:
        conditions = [AuditLog.action.like(f"{prefix}%") for prefix in self._SCORE_RELEVANT_ACTION_PREFIXES]
        changed = self.db.execute(
            select(AuditLog.id)
            .where(
                AuditLog.organization_id == organization_id,
                AuditLog.created_at > since,
                or_(*conditions),
            )
            .limit(1)
        ).scalar_one_or_none()
        return changed is not None

    def _latest_score_snapshot(self, organization_id: uuid.UUID) -> dict | None:
        snapshot = self.db.execute(
            select(ScoreSnapshot)
            .where(ScoreSnapshot.organization_id == organization_id)
            .order_by(ScoreSnapshot.calculated_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if snapshot is None:
            return None

        calculated_at = snapshot.calculated_at
        if calculated_at.tzinfo is None:
            calculated_at = calculated_at.replace(tzinfo=UTC)
        now = self.utcnow()
        age_hours = round((now - calculated_at).total_seconds() / 3600.0, 2)
        stale = age_hours > self.SCORE_SNAPSHOT_STALE_AFTER_HOURS
        underlying_data_changed_since = self._underlying_data_changed_since(organization_id, calculated_at)

        return {
            "id": str(snapshot.id),
            "snapshot_type": snapshot.snapshot_type,
            "score": snapshot.score,
            "grade": snapshot.grade,
            "calculated_at": snapshot.calculated_at,
            "age_hours": age_hours,
            "stale": stale,
            "underlying_data_changed_since": underlying_data_changed_since,
        }

    def posture_summary(self, organization_id: uuid.UUID) -> dict:
        active_frameworks = self._active_framework_rows(organization_id)
        framework_readiness_rows: list[dict] = []
        for _, framework in active_frameworks:
            counts = self._framework_counts(organization_id, framework.id)
            framework_readiness_rows.append(
                {
                    "framework_id": str(framework.id),
                    "name": framework.name,
                    "coverage_pct": counts["control_coverage_pct"],
                }
            )

        total_obligations = int(
            self.db.execute(
                select(func.count(Obligation.id))
                .join(OrganizationFramework, OrganizationFramework.framework_id == Obligation.framework_id)
                .where(
                    OrganizationFramework.organization_id == organization_id,
                    OrganizationFramework.status == "active",
                    Obligation.status == "active",
                )
            ).scalar_one()
        )
        applicable_obligations = int(
            self.db.execute(
                select(func.count(func.distinct(OrganizationObligationState.obligation_id)))
                .join(Obligation, Obligation.id == OrganizationObligationState.obligation_id)
                .join(OrganizationFramework, OrganizationFramework.framework_id == Obligation.framework_id)
                .where(
                    OrganizationObligationState.organization_id == organization_id,
                    OrganizationFramework.organization_id == organization_id,
                    OrganizationFramework.status == "active",
                    Obligation.status == "active",
                    OrganizationObligationState.applicability_status == "applicable",
                )
            ).scalar_one()
        )
        not_applicable_obligations = int(
            self.db.execute(
                select(func.count(func.distinct(OrganizationObligationState.obligation_id)))
                .join(Obligation, Obligation.id == OrganizationObligationState.obligation_id)
                .join(OrganizationFramework, OrganizationFramework.framework_id == Obligation.framework_id)
                .where(
                    OrganizationObligationState.organization_id == organization_id,
                    OrganizationFramework.organization_id == organization_id,
                    OrganizationFramework.status == "active",
                    Obligation.status == "active",
                    OrganizationObligationState.applicability_status == "not_applicable",
                )
            ).scalar_one()
        )

        total_controls = int(
            self.db.execute(
                select(func.count(Control.id)).where(Control.organization_id == organization_id)
            ).scalar_one()
        )
        active_controls = int(
            self.db.execute(
                select(func.count(Control.id)).where(
                    Control.organization_id == organization_id,
                    Control.status != "archived",
                )
            ).scalar_one()
        )

        evidence_summary = EvidenceService(self.db).readiness_summary(organization_id)
        risk_summary = RiskService(self.db).summary(organization_id)
        task_summary = TaskService(self.db).summary(organization_id)
        policy_summary = CompliancePolicyService(self.db).summary(organization_id)
        vendor_summary = VendorService(self.db).summary(organization_id)
        monitoring_summary = ControlMonitoringService(self.db).summary(organization_id)
        monitoring_alert_summary = ControlMonitoringAlertService(self.db).summary(organization_id)

        now = self.utcnow()
        week_end = now + timedelta(days=7)
        due_this_week = int(
            self.db.execute(
                select(func.count(Task.id)).where(
                    Task.organization_id == organization_id,
                    Task.status.in_(["open", "in_progress", "blocked"]),
                    Task.due_date.is_not(None),
                    Task.due_date >= now,
                    Task.due_date <= week_end,
                )
            ).scalar_one()
        )

        open_treatments = int(
            self.db.execute(
                select(func.count(Task.id)).where(
                    Task.organization_id == organization_id,
                    Task.linked_entity_type == "risk",
                    Task.status.in_(["open", "in_progress", "blocked"]),
                )
            ).scalar_one()
        )

        today = self.utcdate()
        expired_policies = int(
            self.db.execute(
                select(func.count(CompliancePolicy.id)).where(
                    CompliancePolicy.organization_id == organization_id,
                    CompliancePolicy.status != "archived",
                    CompliancePolicy.review_due_date.is_not(None),
                    CompliancePolicy.review_due_date < today,
                )
            ).scalar_one()
        )

        pending_assessments = int(
            self.db.execute(
                select(func.count(VendorAssessment.id)).where(
                    VendorAssessment.organization_id == organization_id,
                    VendorAssessment.status.in_(["draft", "in_progress", "under_review"]),
                )
            ).scalar_one()
        )

        upcoming_30_days = int(
            self.db.execute(
                select(func.count(ComplianceDeadline.id)).where(
                    ComplianceDeadline.organization_id == organization_id,
                    ComplianceDeadline.status == "upcoming",
                    ComplianceDeadline.due_date >= today,
                    ComplianceDeadline.due_date <= (today + timedelta(days=30)),
                )
            ).scalar_one()
        )
        overdue_deadlines = int(
            self.db.execute(
                select(func.count(ComplianceDeadline.id)).where(
                    ComplianceDeadline.organization_id == organization_id,
                    ComplianceDeadline.status == "overdue",
                )
            ).scalar_one()
        )

        return {
            "active_frameworks": {
                "count": len(active_frameworks),
                "list": framework_readiness_rows,
            },
            "obligations": {
                "total": total_obligations,
                "applicable": applicable_obligations,
                "not_applicable": not_applicable_obligations,
                "unknown": max(0, total_obligations - applicable_obligations - not_applicable_obligations),
            },
            "controls": {
                "total": total_controls,
                "active": active_controls,
                "with_evidence": max(0, active_controls - int(evidence_summary["controls_without_evidence"])),
                "without_evidence": int(evidence_summary["controls_without_evidence"]),
            },
            "evidence": {
                "total": int(evidence_summary["total_evidence_items"]),
                "verified": int(evidence_summary["verified_evidence_items"]),
                "expired": int(evidence_summary["expired_evidence_items"]),
                "needs_review": int(evidence_summary["needs_review_evidence_items"]),
            },
            "risks": {
                "total": int(risk_summary["total_risks"]),
                "by_severity": {
                    "critical": int(risk_summary["critical_risks"]),
                    "high": int(risk_summary["high_risks"]),
                    "medium": int(risk_summary["medium_risks"]),
                    "low": int(risk_summary["low_risks"]),
                },
                "open_treatments": open_treatments,
            },
            "tasks": {
                "total": int(task_summary["total_tasks"]),
                "overdue": int(task_summary["overdue_tasks"]),
                "due_this_week": due_this_week,
            },
            "policies": {
                "total": int(policy_summary["total_policies"]),
                "approved": int(policy_summary["by_status"].get("approved", 0)),
                "under_review": int(policy_summary["by_status"].get("under_review", 0)),
                "expired": expired_policies,
            },
            "vendors": {
                "total": int(vendor_summary["total_vendors"]),
                "by_risk_tier": dict(vendor_summary["by_risk_tier"]),
                "pending_assessments": pending_assessments,
            },
            "monitoring": {
                "active_definitions": int(monitoring_summary["active_definitions"]),
                "open_alerts": int(monitoring_alert_summary["open_alerts"]),
                "overdue_checks": int(monitoring_summary["definitions_due_now"]),
            },
            "deadlines": {
                "upcoming_30_days": upcoming_30_days,
                "overdue": overdue_deadlines,
            },
        }

    @staticmethod
    def _framework_readiness_insight(counts: dict[str, int | float]) -> str:
        """Synthesizes a short, human-readable explanation of *why* a framework's
        readiness looks the way it does, from counts already computed for the row.
        Never invents data -- only narrates numbers already present in `counts`.
        """
        obligation_count = int(counts["obligation_count"])
        mapped_obligation_count = int(counts["mapped_obligation_count"])
        mapped_control_count = int(counts["mapped_control_count"])
        open_gaps_count = int(counts["open_gaps_count"])
        evidence_verified_pct = float(counts["evidence_verified_pct"])
        control_coverage_pct = float(counts["control_coverage_pct"])

        if obligation_count == 0:
            return "No active obligations defined for this framework yet."

        parts: list[str] = []
        if open_gaps_count > 0:
            parts.append(
                f"{open_gaps_count} of {obligation_count} obligations ({round(100 - control_coverage_pct, 2)}%) "
                "have no mapped control."
            )
        else:
            parts.append(f"All {obligation_count} obligations are mapped to at least one control.")

        if mapped_control_count > 0 and evidence_verified_pct < 100.0:
            unverified_pct = round(100.0 - evidence_verified_pct, 2)
            parts.append(f"{unverified_pct}% of mapped controls lack verified evidence.")
        elif mapped_control_count > 0:
            parts.append("All mapped controls have verified evidence.")

        return " ".join(parts)

    def framework_readiness(self, organization_id: uuid.UUID) -> list[dict]:
        rows = self._active_framework_rows(organization_id)
        latest_snapshot = self._latest_score_snapshot(organization_id)
        response: list[dict] = []
        for _, framework in rows:
            counts = self._framework_counts(organization_id, framework.id)
            response.append(
                {
                    "framework_id": str(framework.id),
                    "name": framework.name,
                    "coverage_level": framework.coverage_level,
                    "obligation_count": int(counts["obligation_count"]),
                    "mapped_control_count": int(counts["mapped_control_count"]),
                    "control_coverage_pct": float(counts["control_coverage_pct"]),
                    "evidence_verified_pct": float(counts["evidence_verified_pct"]),
                    "open_gaps_count": int(counts["open_gaps_count"]),
                    "readiness_insight": self._framework_readiness_insight(counts),
                    "last_score_snapshot": latest_snapshot,
                }
            )
        return response

    def control_health(self, organization_id: uuid.UUID) -> dict:
        by_status_rows = self.db.execute(
            select(Control.status, func.count(Control.id))
            .where(Control.organization_id == organization_id)
            .group_by(Control.status)
        ).all()

        evidence_summary = EvidenceService(self.db).readiness_summary(organization_id)

        controls_with_open_monitoring_alerts = int(
            self.db.execute(
                select(func.count(func.distinct(ControlMonitoringAlert.control_id))).where(
                    ControlMonitoringAlert.organization_id == organization_id,
                    ControlMonitoringAlert.control_id.is_not(None),
                    ControlMonitoringAlert.status == "open",
                )
            ).scalar_one()
        )

        now = self.utcnow()
        overdue_monitoring_control_ids = self.db.execute(
            select(ControlMonitoringDefinition.control_id).where(
                ControlMonitoringDefinition.organization_id == organization_id,
                ControlMonitoringDefinition.status == "active",
                ControlMonitoringDefinition.next_check_due_at.is_not(None),
                ControlMonitoringDefinition.next_check_due_at <= now,
            )
        ).scalars().all()
        overdue_test_control_ids = self.db.execute(
            select(ControlTestDefinition.control_id).where(
                ControlTestDefinition.organization_id == organization_id,
                ControlTestDefinition.status == "active",
                ControlTestDefinition.next_due_at.is_not(None),
                ControlTestDefinition.next_due_at <= now,
            )
        ).scalars().all()
        # A control can have an overdue check tracked by either object: the older
        # ControlMonitoringDefinition, or the more commonly-used ControlTestDefinition/test-run
        # overdue state. Count distinct controls across both so neither overdue-tracking path is
        # silently excluded from this metric.
        controls_with_overdue_checks = len(set(overdue_monitoring_control_ids) | set(overdue_test_control_ids))

        active_controls = int(
            self.db.execute(
                select(func.count(Control.id)).where(
                    Control.organization_id == organization_id,
                    Control.status != "archived",
                )
            ).scalar_one()
        )
        mapped_controls = int(
            self.db.execute(
                select(func.count(func.distinct(ControlObligationMapping.control_id))).where(
                    ControlObligationMapping.organization_id == organization_id,
                    ControlObligationMapping.status == "active",
                )
            ).scalar_one()
        )
        open_high_critical_findings = int(
            self.db.execute(
                select(func.count(AuditFinding.id)).where(
                    AuditFinding.organization_id == organization_id,
                    AuditFinding.deleted_at.is_(None),
                    AuditFinding.severity.in_(["high", "critical"]),
                    AuditFinding.status.not_in(["resolved", "closed", "accepted_risk"]),
                )
            ).scalar_one()
        )

        return {
            "total_controls_by_status": {str(key): int(value) for key, value in by_status_rows},
            "controls_with_no_evidence": int(evidence_summary["controls_without_evidence"]),
            "controls_with_expired_evidence": int(evidence_summary["controls_with_expired_evidence"]),
            "controls_with_open_monitoring_alerts": controls_with_open_monitoring_alerts,
            "controls_with_overdue_checks": controls_with_overdue_checks,
            "controls_mapped_to_0_obligations": max(0, active_controls - mapped_controls),
            "open_high_critical_findings": open_high_critical_findings,
            "health_flag": "at_risk" if open_high_critical_findings > 0 else "normal",
        }

    def risk_heatmap(self, organization_id: uuid.UUID) -> dict:
        risk_heatmap_matrix = RiskService(self.db).heatmap(organization_id)
        vendor_summary = VendorService(self.db).summary(organization_id)

        alert_rows = self.db.execute(
            select(ControlMonitoringAlert.severity, func.count(ControlMonitoringAlert.id))
            .where(
                ControlMonitoringAlert.organization_id == organization_id,
                ControlMonitoringAlert.status == "open",
            )
            .group_by(ControlMonitoringAlert.severity)
        ).all()

        return {
            "risk_heatmap": risk_heatmap_matrix,
            "vendor_risk_distribution": dict(vendor_summary["by_risk_tier"]),
            "open_monitoring_alerts_by_severity": {str(key): int(value) for key, value in alert_rows},
        }

    def recent_activity(self, organization_id: uuid.UUID, limit: int) -> list[dict]:
        action_prefixes = [
            "compliance_policy.",
            "compliance_policy_version.",
            "compliance_policy_approval.",
            "vendor.",
            "vendor_assessment.",
            "vendor_assessment_question.",
            "vendor_risk_score.",
            "compliance_deadline.",
            "control_monitoring_",
            "control.",
            "evidence.",
            "risk.",
            "task.",
        ]

        conditions = [AuditLog.action.like(f"{prefix}%") for prefix in action_prefixes]
        stmt = (
            select(AuditLog)
            .where(
                AuditLog.organization_id == organization_id,
                or_(*conditions),
            )
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        rows = self.db.execute(stmt).scalars().all()
        return [AuditLogRead.model_validate(item).model_dump(mode="json") for item in rows]
