import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.models.ai_governance_review import AIGovernanceReview
from app.models.ai_approval_envelope import AIApprovalEnvelope
from app.models.ai_monitoring_config import AIMonitoringConfig
from app.models.ai_monitoring_reading import AIMonitoringReading
from app.models.ai_system import AISystem
from app.models.shadow_ai_detection import ShadowAIDetection


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
            "_pillar2_status": "not_yet_activated",
        }

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
        except Exception:
            pass

        try:
            # Future: governance controls/attestations coverage query.
            pass
        except Exception:
            pass

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
        except Exception:
            pass

        try:
            # Future: policy violation aggregate query.
            pass
        except Exception:
            pass

        try:
            count = self.db.execute(
                select(func.count(ShadowAIDetection.id)).where(
                    ShadowAIDetection.organization_id == org_id,
                    ShadowAIDetection.status == "new",
                )
            ).scalar_one()
            result["shadow_ai_detected_count"] = int(count or 0)
        except Exception:
            pass

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
        except Exception:
            pass

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
        except Exception:
            pass

        return result
