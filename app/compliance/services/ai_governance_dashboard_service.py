import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.models.ai_governance_review import AIGovernanceReview
from app.models.ai_approval_envelope import AIApprovalEnvelope
from app.models.ai_guardrail_event import AIGuardrailEvent
from app.models.ai_monitoring_config import AIMonitoringConfig
from app.models.ai_monitoring_reading import AIMonitoringReading
from app.models.ai_system import AISystem
from app.models.ai_system_risk_link import AISystemRiskLink
from app.models.risk_control_link import RiskControlLink
from app.models.shadow_ai_detection import ShadowAIDetection

logger = logging.getLogger(__name__)


class AIGovernanceDashboardService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_dashboard(self, org_id: uuid.UUID) -> dict:
        result = {
            "ai_systems_by_tier": {
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
            },
            "governance_coverage_pct": 0.0,
            "outstanding_reviews_count": 0,
            "policy_violations_count": 0,
            "shadow_ai_detected_count": 0,
            "high_risk_systems_without_approval": 0,
            "monitoring_alerts_by_system": [],
            # Metrics whose aggregation query failed. A metric listed here carries its
            # default value only as a placeholder -- the real value is UNKNOWN, not the
            # zero shown. Consumers must render these as "unavailable", never as a real 0,
            # so a query regression can't masquerade as a healthy empty dashboard.
            "unavailable_metrics": [],
            "_pillar2_status": "not_yet_activated",
        }

        def _metric_failed(metric: str, exc: Exception) -> None:
            logger.exception(
                "AI-governance dashboard metric %r failed for org %s", metric, org_id
            )
            result["unavailable_metrics"].append(metric)

        try:
            rows = self.db.execute(
                select(AISystem.risk_tier, func.count(AISystem.id))
                .where(
                    AISystem.organization_id == org_id,
                    AISystem.deleted_at.is_(None),
                )
                .group_by(AISystem.risk_tier)
            ).all()
            for tier, count in rows:
                bucket = str(tier) if tier else "unassessed"
                if bucket not in result["ai_systems_by_tier"]:
                    result["ai_systems_by_tier"][bucket] = 0
                result["ai_systems_by_tier"][bucket] += int(count)
        except Exception as exc:
            _metric_failed("ai_systems_by_tier", exc)

        try:
            # Governance coverage: % of assessed (non-unassessed) AI systems that have
            # either an approved AI approval envelope or at least one active risk->control
            # link via an AI-system risk mapping.
            in_scope = (
                select(func.count(AISystem.id))
                .where(
                    AISystem.organization_id == org_id,
                    AISystem.deleted_at.is_(None),
                    AISystem.risk_tier.isnot(None),
                    AISystem.risk_tier != "unassessed",
                )
            ).scalar_subquery()

            approved_envelope_exists = (
                select(1)
                .select_from(AIApprovalEnvelope)
                .where(
                    AIApprovalEnvelope.organization_id == org_id,
                    AIApprovalEnvelope.ai_system_id == AISystem.id,
                    AIApprovalEnvelope.status == "approved",
                )
            ).correlate(AISystem).exists().select()

            active_control_exists = (
                select(1)
                .select_from(AISystemRiskLink)
                .join(RiskControlLink, RiskControlLink.risk_id == AISystemRiskLink.risk_id)
                .where(
                    AISystemRiskLink.organization_id == org_id,
                    AISystemRiskLink.ai_system_id == AISystem.id,
                    AISystemRiskLink.status == "active",
                    RiskControlLink.status == "active",
                )
            ).correlate(AISystem).exists().select()

            covered_count = self.db.execute(
                select(func.count(AISystem.id))
                .where(
                    AISystem.organization_id == org_id,
                    AISystem.deleted_at.is_(None),
                    AISystem.risk_tier.isnot(None),
                    AISystem.risk_tier != "unassessed",
                    or_(approved_envelope_exists, active_control_exists),
                )
            ).scalar_one()
            total_in_scope = self.db.execute(select(in_scope)).scalar_one()
            if total_in_scope > 0:
                result["governance_coverage_pct"] = round((int(covered_count or 0) / total_in_scope) * 100, 2)
        except Exception as exc:
            _metric_failed("governance_coverage_pct", exc)

        try:
            # Future: outstanding periodic governance reviews query.
            count = self.db.execute(
                select(func.count(AIGovernanceReview.id)).where(
                    AIGovernanceReview.organization_id == org_id,
                    AIGovernanceReview.deleted_at.is_(None),
                    AIGovernanceReview.status.in_(["pending", "in_review"]),
                )
            ).scalar_one()
            result["outstanding_reviews_count"] = int(count or 0)
        except Exception as exc:
            _metric_failed("outstanding_reviews_count", exc)

        try:
            # Policy violations: count recent AI guardrail violation/blocked events.
            # When guardrail events are absent, recent out-of-threshold AI monitoring
            # readings are used as a real proxy for the same operational signal.
            since = datetime.now(UTC) - timedelta(days=30)
            event_count = self.db.execute(
                select(func.count(AIGuardrailEvent.id)).where(
                    AIGuardrailEvent.organization_id == org_id,
                    AIGuardrailEvent.event_type.in_(["violation_detected", "blocked"]),
                    AIGuardrailEvent.created_at >= since,
                )
            ).scalar_one()
            if event_count:
                result["policy_violations_count"] = int(event_count)
            else:
                proxy_count = self.db.execute(
                    select(func.count(AIMonitoringReading.id)).where(
                        AIMonitoringReading.organization_id == org_id,
                        AIMonitoringReading.within_threshold.is_(False),
                        AIMonitoringReading.created_at >= since,
                    )
                ).scalar_one()
                result["policy_violations_count"] = int(proxy_count or 0)
        except Exception as exc:
            _metric_failed("policy_violations_count", exc)

        try:
            count = self.db.execute(
                select(func.count(ShadowAIDetection.id)).where(
                    ShadowAIDetection.organization_id == org_id,
                    ShadowAIDetection.status == "new",
                )
            ).scalar_one()
            result["shadow_ai_detected_count"] = int(count or 0)
        except Exception as exc:
            _metric_failed("shadow_ai_detected_count", exc)

        try:
            approved_systems_subq = (
                select(AIApprovalEnvelope.ai_system_id)
                .where(
                    AIApprovalEnvelope.organization_id == org_id,
                    AIApprovalEnvelope.status == "approved",
                )
                .distinct()
            )
            count = self.db.execute(
                select(func.count(AISystem.id)).where(
                    AISystem.organization_id == org_id,
                    AISystem.deleted_at.is_(None),
                    AISystem.risk_tier.in_(["high", "prohibited"]),
                    AISystem.id.not_in(approved_systems_subq),
                )
            ).scalar_one()
            result["high_risk_systems_without_approval"] = int(count or 0)
        except Exception as exc:
            _metric_failed("high_risk_systems_without_approval", exc)

        try:
            since = datetime.now(UTC) - timedelta(days=30)
            breach_count_expr = func.sum(
                case(
                    (
                        and_(
                            AIMonitoringReading.within_threshold.is_(False),
                            AIMonitoringReading.created_at >= since,
                        ),
                        1,
                    ),
                    else_=0,
                )
            )
            rows = self.db.execute(
                select(
                    AISystem.id,
                    AISystem.name,
                    breach_count_expr.label("breach_count"),
                )
                .join(
                    AIMonitoringConfig,
                    and_(
                        AIMonitoringConfig.organization_id == AISystem.organization_id,
                        AIMonitoringConfig.ai_system_id == AISystem.id,
                        AIMonitoringConfig.deleted_at.is_(None),
                    ),
                )
                .outerjoin(AIMonitoringReading, AIMonitoringReading.config_id == AIMonitoringConfig.id)
                .where(
                    AISystem.organization_id == org_id,
                    AISystem.deleted_at.is_(None),
                )
                .group_by(AISystem.id, AISystem.name)
                .order_by(breach_count_expr.desc(), AISystem.name.asc())
                .limit(5)
            ).all()
            result["monitoring_alerts_by_system"] = [
                {
                    "system_id": str(system_id),
                    "system_name": system_name,
                    "breach_count": int(breach_count or 0),
                }
                for system_id, system_name, breach_count in rows
            ]
        except Exception as exc:
            _metric_failed("monitoring_alerts_by_system", exc)

        return result
