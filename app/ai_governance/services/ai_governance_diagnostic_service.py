from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.ai_governance.services.mlops_adapter_service import MLopsAdapterService
from app.models.ai_governance_diagnostic_snapshot import AIGovernanceDiagnosticSnapshot
from app.models.ai_system import AISystem
from app.models.ai_system_risk_assessment import AISystemRiskAssessment
from app.models.audit_log import AuditLog
from app.models.business_unit import BusinessUnit
from app.models.compliance_risk_recommendation import ComplianceRiskRecommendation
from app.models.eu_ai_act_classification import EUAIActClassification
from app.models.mlflow_connection import MLflowConnection
from app.models.mlflow_drift_event import MLflowDriftEvent
from app.models.mlflow_model_registration import MLflowModelRegistration
from app.services.audit_service import AuditService
from app.services.compliance_dashboard_service import ComplianceDashboardService


class AIGovernanceDiagnosticService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _is_deployed(status_value: str | None) -> bool:
        status = (status_value or "").strip().lower()
        return status in {"deployed", "active", "production"}

    def _require_bu(self, org_id: uuid.UUID, business_unit_id: uuid.UUID | None) -> BusinessUnit | None:
        if business_unit_id is None:
            return None
        bu = self.db.execute(
            select(BusinessUnit).where(
                BusinessUnit.id == business_unit_id,
                BusinessUnit.organization_id == org_id,
                BusinessUnit.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if bu is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business unit not found")
        return bu

    def _latest_completed_assessment(self, org_id: uuid.UUID, ai_system_id: uuid.UUID) -> AISystemRiskAssessment | None:
        return self.db.execute(
            select(AISystemRiskAssessment)
            .where(
                AISystemRiskAssessment.organization_id == org_id,
                AISystemRiskAssessment.ai_system_id == ai_system_id,
                AISystemRiskAssessment.status == "completed",
                AISystemRiskAssessment.archived_at.is_(None),
            )
            .order_by(AISystemRiskAssessment.completed_at.desc(), AISystemRiskAssessment.updated_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    def _assessment_age_days(self, completed_at: datetime | None) -> int | None:
        if completed_at is None:
            return None
        if completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=UTC)
        return max(0, (self.utcnow() - completed_at).days)

    def _eu_ai_act_category(self, org_id: uuid.UUID, ai_system_id: uuid.UUID) -> str | None:
        return self.db.execute(
            select(EUAIActClassification.article_category).where(
                EUAIActClassification.organization_id == org_id,
                EUAIActClassification.ai_system_id == ai_system_id,
            )
        ).scalar_one_or_none()

    def _linked_system_risk_ids(self, org_id: uuid.UUID, ai_system_id: uuid.UUID) -> set[uuid.UUID]:
        reg_risk_ids = self.db.execute(
            select(MLflowModelRegistration.linked_risk_id).where(
                MLflowModelRegistration.organization_id == org_id,
                MLflowModelRegistration.ai_system_id == ai_system_id,
                MLflowModelRegistration.linked_risk_id.is_not(None),
            )
        ).scalars().all()
        drift_risk_ids = self.db.execute(
            select(MLflowDriftEvent.linked_risk_id).where(
                MLflowDriftEvent.organization_id == org_id,
                MLflowDriftEvent.ai_system_id == ai_system_id,
                MLflowDriftEvent.linked_risk_id.is_not(None),
            )
        ).scalars().all()
        return {rid for rid in [*reg_risk_ids, *drift_risk_ids] if rid is not None}

    def _active_drift_alerts(self, org_id: uuid.UUID, ai_system_id: uuid.UUID) -> list[MLflowDriftEvent]:
        now = self.utcnow()
        return self.db.execute(
            select(MLflowDriftEvent).where(
                MLflowDriftEvent.organization_id == org_id,
                MLflowDriftEvent.ai_system_id == ai_system_id,
                MLflowDriftEvent.severity.in_(["high", "critical"]),
                MLflowDriftEvent.detected_at >= (now - timedelta(days=30)),
            )
        ).scalars().all()

    def _has_active_mlflow_connection(self, org_id: uuid.UUID) -> bool:
        return bool(
            self.db.execute(
                select(func.count(MLflowConnection.id)).where(
                    MLflowConnection.organization_id == org_id,
                    MLflowConnection.is_active.is_(True),
                )
            ).scalar_one()
        )

    def _open_compliance_recommendation_count(self, org_id: uuid.UUID, ai_system_id: uuid.UUID) -> int:
        risk_ids = self._linked_system_risk_ids(org_id, ai_system_id)
        if not risk_ids:
            return 0
        return int(
            self.db.execute(
                select(func.count(ComplianceRiskRecommendation.id)).where(
                    ComplianceRiskRecommendation.organization_id == org_id,
                    ComplianceRiskRecommendation.status == "pending",
                    ComplianceRiskRecommendation.linked_risk_id.in_(list(risk_ids)),
                )
            ).scalar_one()
        )

    def _has_recent_audit_activity(self, org_id: uuid.UUID, ai_system_id: uuid.UUID) -> bool:
        cutoff = self.utcnow() - timedelta(days=90)
        count = self.db.execute(
            select(func.count(AuditLog.id)).where(
                AuditLog.organization_id == org_id,
                AuditLog.entity_id == ai_system_id,
                AuditLog.entity_type.in_(["ai_system", "ai_systems"]),
                AuditLog.created_at >= cutoff,
            )
        ).scalar_one()
        return int(count) > 0

    def _system_summary(self, org_id: uuid.UUID, system: AISystem, mlops_service: MLopsAdapterService) -> dict:
        assessment = self._latest_completed_assessment(org_id, system.id)
        has_completed_assessment = assessment is not None
        assessment_age_days = self._assessment_age_days(assessment.completed_at if assessment else None)
        stale_assessment = assessment_age_days is not None and assessment_age_days > 365

        mlops_coverage = mlops_service.get_mlops_coverage(org_id=org_id, ai_system_id=system.id)
        mlflow_connected = bool(mlops_coverage.get("is_mlflow_connected", False))
        has_active_mlflow_connection = self._has_active_mlflow_connection(org_id)
        latest_model_version = mlops_coverage.get("latest_model_version")
        active_drift_events = self._active_drift_alerts(org_id, system.id)
        active_drift_alerts = len(active_drift_events)
        unresolved_drift_alerts = sum(1 for item in active_drift_events if item.linked_risk_id is None)

        open_compliance_recommendations = self._open_compliance_recommendation_count(org_id, system.id)
        eu_ai_act_risk_category = self._eu_ai_act_category(org_id, system.id)

        gaps: list[str] = []
        if not has_completed_assessment:
            gaps.append("No completed risk assessment")
        if stale_assessment:
            gaps.append("Risk assessment older than 12 months")
        if unresolved_drift_alerts > 0:
            gaps.append("High/critical model drift detected — no risk raised")
        if self._is_deployed(system.deployment_status) and not has_active_mlflow_connection:
            gaps.append("Deployed with no MLflow monitoring connected")
        if not self._has_recent_audit_activity(org_id, system.id):
            gaps.append("No audit trail entries in last 90 days")

        if self._is_deployed(system.deployment_status) and not has_completed_assessment:
            system_health = "critical"
        elif active_drift_alerts > 0 or stale_assessment:
            system_health = "at_risk"
        elif open_compliance_recommendations > 0:
            system_health = "needs_attention"
        else:
            system_health = "good"

        return {
            "ai_system_id": str(system.id),
            "name": system.name,
            "lifecycle_status": system.lifecycle_status,
            "deployment_status": system.deployment_status,
            "has_completed_risk_assessment": has_completed_assessment,
            "risk_assessment_age_days": assessment_age_days,
            "mlflow_connected": mlflow_connected,
            "latest_model_version": latest_model_version,
            "active_drift_alerts": active_drift_alerts,
            "open_compliance_recommendations": open_compliance_recommendations,
            "eu_ai_act_risk_category": eu_ai_act_risk_category,
            "governance_gaps": gaps,
            "system_health": system_health,
        }

    @staticmethod
    def _health_from_score(score: float) -> str:
        if score >= 80:
            return "good"
        if score >= 60:
            return "needs_attention"
        if score >= 40:
            return "at_risk"
        return "critical"

    def generate_diagnostic(
        self,
        *,
        org_id: uuid.UUID,
        generated_by: uuid.UUID,
        business_unit_id: uuid.UUID | None = None,
        snapshot_label: str | None = None,
    ) -> AIGovernanceDiagnosticSnapshot:
        bu = self._require_bu(org_id, business_unit_id)

        systems_stmt = select(AISystem).where(
            AISystem.organization_id == org_id,
            AISystem.deleted_at.is_(None),
        )
        if business_unit_id is not None:
            systems_stmt = systems_stmt.where(AISystem.business_unit_id == business_unit_id)
        systems = self.db.execute(systems_stmt.order_by(AISystem.name.asc())).scalars().all()

        mlops_service = MLopsAdapterService(self.db)
        system_summaries = [self._system_summary(org_id, system, mlops_service) for system in systems]

        total = len(system_summaries)
        if total == 0:
            score = Decimal("0.00")
            overall_health = "needs_attention"
            org_summary = {
                "total_ai_systems": 0,
                "systems_with_completed_assessment": 0,
                "systems_with_mlflow_monitoring": 0,
                "systems_with_active_drift_alerts": 0,
                "systems_deployed_without_assessment": 0,
                "total_active_drift_alerts": 0,
                "total_open_compliance_recommendations": 0,
                "eu_ai_act_high_risk_systems": 0,
                "critical_gap_systems": [],
            }
            critical_gaps_count = 0
        else:
            systems_with_completed_assessment = sum(1 for row in system_summaries if row["has_completed_risk_assessment"])
            systems_with_mlflow_monitoring = sum(1 for row in system_summaries if row["mlflow_connected"])
            systems_with_active_drift_alerts = sum(1 for row in system_summaries if row["active_drift_alerts"] > 0)
            systems_deployed_without_assessment = sum(
                1
                for row in system_summaries
                if self._is_deployed(str(row["deployment_status"])) and not row["has_completed_risk_assessment"]
            )
            total_active_drift_alerts = sum(int(row["active_drift_alerts"]) for row in system_summaries)
            total_open_compliance_recommendations = sum(
                int(row["open_compliance_recommendations"]) for row in system_summaries
            )
            eu_ai_act_high_risk_systems = sum(
                1 for row in system_summaries if row["eu_ai_act_risk_category"] in {"high_risk_annex1", "high_risk_annex3"}
            )
            critical_gap_systems = [str(row["name"]) for row in system_summaries if row["system_health"] == "critical"]
            critical_gaps_count = len(critical_gap_systems)

            # Weighted governance score:
            # 40% completed assessments + 25% MLflow monitoring +
            # 20% systems with zero active drift alerts + 15% systems with zero critical gaps.
            pct_completed_assessment = (systems_with_completed_assessment / total) * 100
            pct_mlflow_monitored = (systems_with_mlflow_monitoring / total) * 100
            pct_zero_drift = ((total - systems_with_active_drift_alerts) / total) * 100
            pct_zero_critical = ((total - critical_gaps_count) / total) * 100

            weighted_score = (
                (0.40 * pct_completed_assessment)
                + (0.25 * pct_mlflow_monitored)
                + (0.20 * pct_zero_drift)
                + (0.15 * pct_zero_critical)
            )
            score = Decimal(str(weighted_score)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            overall_health = self._health_from_score(float(score))

            org_summary = {
                "total_ai_systems": total,
                "systems_with_completed_assessment": systems_with_completed_assessment,
                "systems_with_mlflow_monitoring": systems_with_mlflow_monitoring,
                "systems_with_active_drift_alerts": systems_with_active_drift_alerts,
                "systems_deployed_without_assessment": systems_deployed_without_assessment,
                "total_active_drift_alerts": total_active_drift_alerts,
                "total_open_compliance_recommendations": total_open_compliance_recommendations,
                "eu_ai_act_high_risk_systems": eu_ai_act_high_risk_systems,
                "critical_gap_systems": critical_gap_systems,
            }

        posture = ComplianceDashboardService(self.db).posture_summary(org_id)
        snapshot_data = {
            "scope": {
                "organization_id": str(org_id),
                "business_unit_id": str(business_unit_id) if business_unit_id else None,
                "business_unit_name": bu.name if bu else None,
            },
            "ai_systems_summary": system_summaries,
            "org_level_summary": org_summary,
            "posture_summary": {
                "framework_coverage_pct": float(
                    posture.get("active_frameworks", {}).get("average_coverage_pct", 0) or 0
                ),
                "control_effectiveness_pct": float(
                    posture.get("monitoring", {}).get("coverage_pct", 0) or 0
                ),
                "open_gaps_count": int(posture.get("obligations", {}).get("unknown", 0) or 0),
            },
            "overall_governance_score": float(score),
            "overall_health": overall_health,
            "generated_at": self.utcnow().isoformat(),
        }

        row = AIGovernanceDiagnosticSnapshot(
            organization_id=org_id,
            business_unit_id=business_unit_id,
            generated_by=generated_by,
            snapshot_label=snapshot_label,
            overall_governance_score=score,
            overall_health=overall_health,
            snapshot_data=snapshot_data,
            ai_systems_assessed=total,
            critical_gaps_count=critical_gaps_count,
        )
        self.db.add(row)
        self.db.flush()

        self.audit.write_audit_log(
            action="ai_governance.diagnostic_generated",
            entity_type="ai_governance_diagnostic_snapshot",
            organization_id=org_id,
            actor_user_id=generated_by,
            entity_id=row.id,
            metadata_json={
                "ai_systems_assessed": total,
                "overall_governance_score": float(score),
                "critical_gaps_count": critical_gaps_count,
                "provider_used": None,
                "business_unit_id": str(business_unit_id) if business_unit_id else None,
            },
        )
        return row

    def list_diagnostics(
        self,
        *,
        org_id: uuid.UUID,
        business_unit_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[AIGovernanceDiagnosticSnapshot], int]:
        stmt = select(AIGovernanceDiagnosticSnapshot).where(
            AIGovernanceDiagnosticSnapshot.organization_id == org_id,
        )
        if business_unit_id is not None:
            stmt = stmt.where(AIGovernanceDiagnosticSnapshot.business_unit_id == business_unit_id)

        total = int(self.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
        rows = self.db.execute(
            stmt.order_by(AIGovernanceDiagnosticSnapshot.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars().all()
        return rows, total

    def get_diagnostic(self, *, org_id: uuid.UUID, snapshot_id: uuid.UUID) -> AIGovernanceDiagnosticSnapshot:
        row = self.db.execute(
            select(AIGovernanceDiagnosticSnapshot).where(
                AIGovernanceDiagnosticSnapshot.id == snapshot_id,
                AIGovernanceDiagnosticSnapshot.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI governance diagnostic snapshot not found")
        return row
