from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.orm import Session

from app.ai_governance.services.ai_provider_service import AIProviderService
from app.models.business_unit import BusinessUnit
from app.models.compliance_risk_recommendation import ComplianceRiskRecommendation
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.risk import Risk
from app.models.risk_indicator import RiskIndicator
from app.compliance.services.risk_scoring_service import RiskScoringService
from app.services.audit_service import AuditService
from app.services.compliance_dashboard_service import ComplianceDashboardService
from app.services.risk_service import RiskService
from app.core.validation import validate_choice


ALLOWED_RECOMMENDATION_TYPES = {
    "gap_identified",
    "treatment_change",
    "new_risk",
    "risk_retirement",
}
ALLOWED_LIST_STATUS = {"pending", "accepted", "dismissed", "snoozed"}
ALLOWED_TREATMENT_STRATEGIES = {"mitigate", "accept", "transfer", "avoid", "undecided"}


class ComplianceRiskRecommendationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.ai_provider = AIProviderService(db)
        self.audit = AuditService(db)

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

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

    def _risk_filters(self, org_id: uuid.UUID, business_unit_id: uuid.UUID | None):
        filters = [Risk.organization_id == org_id]
        if business_unit_id is not None:
            filters.append(Risk.business_unit_id == business_unit_id)
        return filters

    def _kri_breach_count(self, org_id: uuid.UUID) -> int:
        # Matches existing KRI summary semantics: red/amber are breaches.
        return int(
            self.db.execute(
                select(func.count(RiskIndicator.id)).where(
                    RiskIndicator.organization_id == org_id,
                    RiskIndicator.is_active.is_(True),
                    RiskIndicator.archived_at.is_(None),
                    RiskIndicator.status.in_(["red", "amber"]),
                )
            ).scalar_one()
        )

    def _appetite_breach_count(self, org_id: uuid.UUID, business_unit_id: uuid.UUID | None) -> int:
        rows = self.db.execute(
            select(ControlMonitoringAlert).where(
                ControlMonitoringAlert.organization_id == org_id,
                ControlMonitoringAlert.alert_type == "risk_threshold_breach",
                ControlMonitoringAlert.status == "open",
            )
        ).scalars().all()

        if business_unit_id is None:
            return len(rows)

        filtered = 0
        bu_text = str(business_unit_id)
        for row in rows:
            ctx = row.alert_context_json if isinstance(row.alert_context_json, dict) else {}
            if str(ctx.get("scope_id") or "") == bu_text:
                filtered += 1
                continue

            raw_risk_id = ctx.get("risk_id")
            if not isinstance(raw_risk_id, str):
                continue
            try:
                risk_id = uuid.UUID(raw_risk_id)
            except ValueError:
                continue

            risk = self.db.get(Risk, risk_id)
            if risk and risk.organization_id == org_id and risk.business_unit_id == business_unit_id:
                filtered += 1

        return filtered

    def _context_data(self, org_id: uuid.UUID, business_unit_id: uuid.UUID | None) -> dict:
        bu = self._require_bu(org_id, business_unit_id)

        risk_filters = self._risk_filters(org_id, business_unit_id)
        category_rows = self.db.execute(
            select(Risk.category, func.count(Risk.id)).where(and_(*risk_filters)).group_by(Risk.category)
        ).all()
        severity_rows = self.db.execute(
            select(Risk.severity, func.count(Risk.id)).where(and_(*risk_filters)).group_by(Risk.severity)
        ).all()
        top_rows = self.db.execute(
            select(Risk.title, Risk.inherent_score)
            .where(and_(*risk_filters))
            .order_by(desc(Risk.inherent_score), desc(Risk.created_at))
            .limit(5)
        ).all()

        posture = ComplianceDashboardService(self.db).posture_summary(org_id)
        framework_rows = posture.get("active_frameworks", {}).get("list", [])
        coverage_vals = [float(row.get("coverage_pct", 0.0)) for row in framework_rows if isinstance(row, dict)]
        framework_coverage_pct = round(sum(coverage_vals) / len(coverage_vals), 2) if coverage_vals else 0.0

        controls_total = int(posture.get("controls", {}).get("active", 0) or 0)
        controls_without_evidence = int(posture.get("controls", {}).get("without_evidence", 0) or 0)
        control_effectiveness_pct = round((max(0.0, 1.0 - (controls_without_evidence / max(controls_total, 1))) * 100.0), 2)

        open_gaps_count = int(posture.get("obligations", {}).get("unknown", 0) or 0)

        return {
            "risk_count_by_category": {str(k): int(v) for k, v in category_rows},
            "risk_count_by_severity": {str(k): int(v) for k, v in severity_rows},
            "top_risks": [{"title": str(title), "score": int(score or 0)} for title, score in top_rows],
            "framework_coverage_pct": framework_coverage_pct,
            "control_effectiveness_pct": control_effectiveness_pct,
            "open_gaps_count": open_gaps_count,
            "kri_breach_count": self._kri_breach_count(org_id),
            "appetite_breach_count": self._appetite_breach_count(org_id, business_unit_id),
            "business_unit_name": bu.name if bu else None,
        }

    def _resolve_linked_risk_id(self, org_id: uuid.UUID, linked_risk_title: str | None) -> uuid.UUID | None:
        if not linked_risk_title:
            return None
        title = linked_risk_title.strip()
        if not title:
            return None

        rows = self.db.execute(
            select(Risk.id).where(
                Risk.organization_id == org_id,
                Risk.title.ilike(f"%{title}%"),
            )
        ).scalars().all()
        if len(rows) == 1:
            return rows[0]
        return None

    def _get_recommendation(self, org_id: uuid.UUID, recommendation_id: uuid.UUID) -> ComplianceRiskRecommendation:
        row = self.db.execute(
            select(ComplianceRiskRecommendation).where(
                ComplianceRiskRecommendation.id == recommendation_id,
                ComplianceRiskRecommendation.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compliance risk recommendation not found")
        return row

    def generate_recommendations(
        self,
        *,
        org_id: uuid.UUID,
        generated_by: uuid.UUID,
        business_unit_id: uuid.UUID | None = None,
    ) -> list[ComplianceRiskRecommendation]:
        self._require_bu(org_id, business_unit_id)
        context_data = self._context_data(org_id, business_unit_id)

        recommendations, provider_used, used_byo_credentials = self.ai_provider.generate_risk_recommendations(
            org_id=org_id,
            context_data=context_data,
            business_unit_id=business_unit_id,
        )

        now = self.utcnow()
        rows: list[ComplianceRiskRecommendation] = []
        for item in recommendations:
            rec_type = str(item.get("recommendation_type", "")).strip()
            if rec_type not in ALLOWED_RECOMMENDATION_TYPES:
                continue

            row = ComplianceRiskRecommendation(
                organization_id=org_id,
                business_unit_id=business_unit_id,
                recommendation_type=rec_type,
                title=str(item.get("title", "")).strip()[:300],
                rationale=str(item.get("rationale", "")).strip(),
                suggested_category=(str(item.get("suggested_category")).strip() if item.get("suggested_category") is not None else None),
                suggested_likelihood=item.get("suggested_likelihood"),
                suggested_impact=item.get("suggested_impact"),
                suggested_treatment=(str(item.get("suggested_treatment")).strip() if item.get("suggested_treatment") is not None else None),
                linked_risk_id=self._resolve_linked_risk_id(org_id, item.get("linked_risk_title")),
                context_snapshot_json=context_data,
                provider_used=provider_used,
                used_byo_credentials=used_byo_credentials,
                status="pending",
                accepted_risk_id=None,
                generated_by=generated_by,
                accepted_by=None,
                dismissed_by=None,
                snoozed_until=None,
                created_at=now,
                updated_at=now,
            )
            self.db.add(row)
            self.db.flush()
            rows.append(row)

        self.audit.write_audit_log(
            action="compliance_risk.recommendations_generated",
            entity_type="compliance_risk_recommendations",
            organization_id=org_id,
            actor_user_id=generated_by,
            metadata_json={
                "count": len(rows),
                "provider_used": provider_used,
                "business_unit_id": str(business_unit_id) if business_unit_id else None,
            },
        )

        return rows

    def _create_risk_from_recommendation(
        self,
        *,
        org_id: uuid.UUID,
        recommendation: ComplianceRiskRecommendation,
        accepted_by: uuid.UUID,
    ) -> Risk:
        likelihood = max(1, min(5, int(recommendation.suggested_likelihood or 3)))
        impact = max(1, min(5, int(recommendation.suggested_impact or 3)))

        treatment_strategy = str(recommendation.suggested_treatment or "undecided").strip().lower()
        if treatment_strategy not in ALLOWED_TREATMENT_STRATEGIES:
            treatment_strategy = "undecided"

        risk = Risk(
            organization_id=org_id,
            title=recommendation.title[:255],
            description=recommendation.rationale,
            category=(recommendation.suggested_category or "other")[:32],
            status="identified",
            severity="low",
            likelihood=likelihood,
            impact=impact,
            treatment_strategy=treatment_strategy,
            business_unit_id=recommendation.business_unit_id,
            created_by_user_id=accepted_by,
            metadata_json={
                "source": "compliance_risk_recommendation",
                "recommendation_id": str(recommendation.id),
            },
        )

        settings = RiskScoringService.get_or_create_org_settings(org_id, self.db)
        score = RiskScoringService.compute_score(risk, settings)
        risk.inherent_score = score
        risk.severity = RiskService.score_to_severity(score)

        self.db.add(risk)
        self.db.flush()
        RiskService(self.db).check_appetite_breach(organization_id=org_id, risk=risk, actor_user_id=accepted_by)
        return risk

    def accept_recommendation(
        self,
        *,
        org_id: uuid.UUID,
        recommendation_id: uuid.UUID,
        accepted_by: uuid.UUID,
    ) -> tuple[ComplianceRiskRecommendation, uuid.UUID | None]:
        row = self._get_recommendation(org_id, recommendation_id)

        created_or_updated_risk_id: uuid.UUID | None = None

        if row.recommendation_type in {"new_risk", "gap_identified"}:
            risk = self._create_risk_from_recommendation(
                org_id=org_id,
                recommendation=row,
                accepted_by=accepted_by,
            )
            created_or_updated_risk_id = risk.id
            row.accepted_risk_id = risk.id

        elif row.recommendation_type == "treatment_change":
            if row.linked_risk_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="treatment_change recommendation requires linked_risk_id",
                )
            risk = self.db.execute(
                select(Risk).where(
                    Risk.id == row.linked_risk_id,
                    Risk.organization_id == org_id,
                )
            ).scalar_one_or_none()
            if risk is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked risk not found")

            new_strategy = str(row.suggested_treatment or "").strip().lower()
            if not new_strategy or new_strategy not in ALLOWED_TREATMENT_STRATEGIES:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="suggested_treatment must map to a valid treatment strategy",
                )
            risk.treatment_strategy = new_strategy
            created_or_updated_risk_id = risk.id

        elif row.recommendation_type == "risk_retirement":
            if row.linked_risk_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="risk_retirement recommendation requires linked_risk_id",
                )
            risk = self.db.execute(
                select(Risk).where(
                    Risk.id == row.linked_risk_id,
                    Risk.organization_id == org_id,
                )
            ).scalar_one_or_none()
            if risk is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked risk not found")
            risk.status = "archived"
            created_or_updated_risk_id = risk.id

        row.status = "accepted"
        row.accepted_by = accepted_by
        row.updated_at = self.utcnow()
        self.db.flush()

        self.audit.write_audit_log(
            action="compliance_risk.recommendation_accepted",
            entity_type="compliance_risk_recommendations",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=accepted_by,
            metadata_json={
                "recommendation_type": row.recommendation_type,
                "accepted_risk_id": str(row.accepted_risk_id) if row.accepted_risk_id else None,
                "created_or_updated_risk_id": str(created_or_updated_risk_id) if created_or_updated_risk_id else None,
            },
        )

        return row, created_or_updated_risk_id

    def dismiss_recommendation(
        self,
        *,
        org_id: uuid.UUID,
        recommendation_id: uuid.UUID,
        dismissed_by: uuid.UUID,
    ) -> ComplianceRiskRecommendation:
        row = self._get_recommendation(org_id, recommendation_id)
        row.status = "dismissed"
        row.dismissed_by = dismissed_by
        row.updated_at = self.utcnow()
        self.db.flush()

        self.audit.write_audit_log(
            action="compliance_risk.recommendation_dismissed",
            entity_type="compliance_risk_recommendations",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=dismissed_by,
            metadata_json={"status": row.status},
        )

        return row

    def snooze_recommendation(
        self,
        *,
        org_id: uuid.UUID,
        recommendation_id: uuid.UUID,
        snoozed_until: datetime,
        actor_user_id: uuid.UUID,
    ) -> ComplianceRiskRecommendation:
        row = self._get_recommendation(org_id, recommendation_id)
        row.status = "snoozed"
        row.snoozed_until = snoozed_until
        row.updated_at = self.utcnow()
        self.db.flush()

        self.audit.write_audit_log(
            action="compliance_risk.recommendation_snoozed",
            entity_type="compliance_risk_recommendations",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            metadata_json={"snoozed_until": snoozed_until.isoformat()},
        )

        return row

    def list_recommendations(
        self,
        *,
        org_id: uuid.UUID,
        status_filter: str | None = None,
        recommendation_type: str | None = None,
        business_unit_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ComplianceRiskRecommendation], int]:
        stmt = select(ComplianceRiskRecommendation).where(ComplianceRiskRecommendation.organization_id == org_id)

        if recommendation_type is not None:
            stmt = stmt.where(ComplianceRiskRecommendation.recommendation_type == recommendation_type)

        if business_unit_id is not None:
            stmt = stmt.where(ComplianceRiskRecommendation.business_unit_id == business_unit_id)

        now = self.utcnow()
        if status_filter:
            status_filter = validate_choice(status_filter, ALLOWED_LIST_STATUS, "status")
            if status_filter == "pending":
                stmt = stmt.where(
                    or_(
                        ComplianceRiskRecommendation.status == "pending",
                        and_(
                            ComplianceRiskRecommendation.status == "snoozed",
                            ComplianceRiskRecommendation.snoozed_until.is_not(None),
                            ComplianceRiskRecommendation.snoozed_until < now,
                        ),
                    )
                )
            else:
                stmt = stmt.where(ComplianceRiskRecommendation.status == status_filter)

        total = int(self.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
        rows = self.db.execute(
            stmt.order_by(ComplianceRiskRecommendation.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars().all()
        return rows, total

    def get_recommendation(self, *, org_id: uuid.UUID, recommendation_id: uuid.UUID) -> ComplianceRiskRecommendation:
        return self._get_recommendation(org_id, recommendation_id)
