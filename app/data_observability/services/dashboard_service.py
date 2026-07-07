import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import Integer, func, or_, select
from sqlalchemy.orm import Session

from app.models.data_asset import DataAsset
from app.models.data_incident import DataIncident
from app.models.data_quality_config import DataQualityConfig
from app.models.data_quality_reading import DataQualityReading
from app.models.data_retention_review import DataRetentionReview
from app.data_observability.services.data_obligation_service import DataObligationService


class DataObservabilityDashboardService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def get_dashboard(self, org_id: uuid.UUID) -> dict:
        total_assets = int(
            self.db.execute(
                select(func.count(DataAsset.id)).where(
                    DataAsset.organization_id == org_id,
                    DataAsset.deleted_at.is_(None),
                )
            ).scalar_one()
            or 0
        )

        classified = int(
            self.db.execute(
                select(func.count(DataAsset.id)).where(
                    DataAsset.organization_id == org_id,
                    DataAsset.classification_type.is_not(None),
                    DataAsset.classification_type != "unclassified",
                    DataAsset.deleted_at.is_(None),
                )
            ).scalar_one()
            or 0
        )

        confirmed = int(
            self.db.execute(
                select(func.count(DataAsset.id)).where(
                    DataAsset.organization_id == org_id,
                    DataAsset.classification_confirmed.is_(True),
                    DataAsset.deleted_at.is_(None),
                )
            ).scalar_one()
            or 0
        )

        by_sensitivity: dict[str, int] = {}
        for tier in ["public", "internal", "confidential", "restricted", "secret"]:
            by_sensitivity[tier] = int(
                self.db.execute(
                    select(func.count(DataAsset.id)).where(
                        DataAsset.organization_id == org_id,
                        DataAsset.sensitivity_tier == tier,
                        DataAsset.deleted_at.is_(None),
                    )
                ).scalar_one()
                or 0
            )

        # Aggregate in SQL rather than pulling every reading row into Python: an org with a
        # heavily-instrumented data estate can easily generate thousands of readings/week,
        # and this endpoint only needs the counts, not the rows themselves.
        since = self.utcnow() - timedelta(days=7)
        readings_total, readings_breach = self.db.execute(
            select(
                func.count(DataQualityReading.id),
                func.coalesce(func.sum(func.cast(DataQualityReading.within_threshold.is_(False), Integer)), 0),
            )
            .join(DataQualityConfig, DataQualityConfig.id == DataQualityReading.config_id)
            .where(
                DataQualityConfig.organization_id == org_id,
                DataQualityReading.created_at >= since,
            )
        ).one()
        readings_total = int(readings_total or 0)
        quality_breach_count = int(readings_breach or 0)
        quality_pass_count = readings_total - quality_breach_count

        anomaly_count = int(
            self.db.execute(
                select(func.count(DataIncident.id)).where(
                    DataIncident.organization_id == org_id,
                    DataIncident.detector_type == "anomaly_rule",
                    DataIncident.detected_at >= since,
                    DataIncident.status != "dismissed",
                )
            ).scalar_one()
            or 0
        )

        assets_with_policy = int(
            self.db.execute(
                select(func.count(DataAsset.id)).where(
                    DataAsset.organization_id == org_id,
                    DataAsset.retention_policy_days.is_not(None),
                    DataAsset.deleted_at.is_(None),
                )
            ).scalar_one()
            or 0
        )

        pending_retention = int(
            self.db.execute(
                select(func.count(DataRetentionReview.id)).where(
                    DataRetentionReview.organization_id == org_id,
                    DataRetentionReview.status == "pending",
                )
            ).scalar_one()
            or 0
        )

        retention_compliance_rate = ((assets_with_policy - pending_retention) / assets_with_policy * 100.0) if assets_with_policy > 0 else 100.0

        by_severity: dict[str, int] = {}
        for sev in ["critical", "high", "medium", "low"]:
            by_severity[sev] = int(
                self.db.execute(
                    select(func.count(DataIncident.id)).where(
                        DataIncident.organization_id == org_id,
                        DataIncident.severity == sev,
                        DataIncident.status.in_(["new", "investigating", "contained"]),
                    )
                ).scalar_one()
                or 0
            )

        needs_review = int(
            self.db.execute(
                select(func.count(DataAsset.id)).where(
                    DataAsset.organization_id == org_id,
                    DataAsset.deleted_at.is_(None),
                    or_(
                        DataAsset.classification_type.is_(None),
                        DataAsset.classification_type == "unclassified",
                        DataAsset.classification_confirmed.is_(False),
                        DataAsset.classification_confidence < 0.5,
                    ),
                )
            ).scalar_one()
            or 0
        )

        obligation_coverage = DataObligationService(self.db).get_coverage_summary(org_id)
        breach_rate_7d = (quality_breach_count / readings_total * 100.0) if readings_total else 0.0
        active_incidents = sum(by_severity.values())

        insights = self._build_insights(
            total_assets=total_assets,
            needs_review=needs_review,
            breach_rate_7d=breach_rate_7d,
            readings_total=readings_total,
            active_incidents=active_incidents,
            by_severity=by_severity,
            pending_retention=pending_retention,
        )

        return {
            "asset_coverage": {
                "total_assets": total_assets,
                "classified_count": classified,
                "confirmed_count": confirmed,
                "classification_coverage_pct": (classified / total_assets * 100.0) if total_assets > 0 else 0.0,
                "by_sensitivity_tier": by_sensitivity,
                "needs_review_count": needs_review,
            },
            "quality_metrics": {
                "readings_last_7d": readings_total,
                "breach_count_7d": quality_breach_count,
                "pass_count_7d": quality_pass_count,
                "breach_rate_7d": breach_rate_7d,
            },
            "access_anomalies": {
                "anomaly_count_7d": anomaly_count,
                "active_incidents": active_incidents,
                "by_severity": by_severity,
            },
            "retention": {
                "assets_with_policy": assets_with_policy,
                "pending_reviews": pending_retention,
                "retention_compliance_rate": round(retention_compliance_rate, 2),
            },
            "data_obligation_coverage": obligation_coverage,
            "insights": insights,
            "generated_at": self.utcnow().isoformat(),
        }

    @staticmethod
    def _build_insights(
        *,
        total_assets: int,
        needs_review: int,
        breach_rate_7d: float,
        readings_total: int,
        active_incidents: int,
        by_severity: dict[str, int],
        pending_retention: int,
    ) -> list[str]:
        """Synthesizes plain-language callouts from counts already computed above, so the
        dashboard surfaces *why* it looks the way it does instead of only raw numbers.
        """
        insights: list[str] = []

        if total_assets == 0:
            insights.append("No data assets have been registered yet.")
            return insights

        if needs_review > 0:
            pct = round(needs_review / total_assets * 100.0, 1)
            insights.append(
                f"{needs_review} of {total_assets} assets ({pct}%) need classification review "
                "(unclassified, unconfirmed, or low-confidence)."
            )

        if readings_total > 0 and breach_rate_7d > 0:
            insights.append(
                f"{round(breach_rate_7d, 1)}% of data quality readings in the last 7 days breached their threshold."
            )

        critical_or_high = int(by_severity.get("critical", 0)) + int(by_severity.get("high", 0))
        if critical_or_high > 0:
            insights.append(f"{critical_or_high} critical/high-severity access incidents are still open.")
        elif active_incidents > 0:
            insights.append(f"{active_incidents} lower-severity access incidents are still open.")

        if pending_retention > 0:
            insights.append(f"{pending_retention} retention reviews are pending action.")

        if not insights:
            insights.append("No outstanding data observability issues detected.")

        return insights
