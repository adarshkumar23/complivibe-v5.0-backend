import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.compliance.services.board_scorecard_builder import BoardScorecardBuilder
from app.compliance.services.issue_policy_link_service import IssuePolicyLinkService
from app.models.ai_system import AISystem
from app.models.compliance_certification import ComplianceCertification
from app.models.compliance_policy import CompliancePolicy
from app.models.compliance_report import ComplianceReport
from app.models.compliance_deadline import ComplianceDeadline
from app.models.control import Control
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.custom_report_template import CustomReportTemplate
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.framework import Framework
from app.models.issue import Issue
from app.models.issue_sla_tracking import IssueSLATracking
from app.models.obligation import Obligation
from app.models.policy_attestation_record import PolicyAttestationRecord
from app.models.risk import Risk
from app.models.score_snapshot import ScoreSnapshot
from app.models.vendor import Vendor
from app.models.vendor_assessment import VendorAssessment
from app.models.vendor_questionnaire_response import VendorQuestionnaireResponse
from app.services.scoring_service import ScoringService


SECTION_NAMES = {
    "executive_summary",
    "framework_readiness",
    "control_health",
    "risk_summary",
    "vendor_risk",
    "evidence_status",
    "open_issues",
    "policy_status",
    "ai_governance_summary",
}


class CustomReportGenerator:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _today() -> date:
        return datetime.now(UTC).date()

    def _framework_ids_in_scope(self, org_id: uuid.UUID, framework_filter: list[str] | list[uuid.UUID] | dict | None) -> list[uuid.UUID]:
        stmt = (
            select(Framework.id)
            .join(Obligation, Obligation.framework_id == Framework.id)
            .join(ControlObligationMapping, ControlObligationMapping.obligation_id == Obligation.id)
            .where(
                ControlObligationMapping.organization_id == org_id,
                ControlObligationMapping.status == "active",
            )
            .group_by(Framework.id)
        )
        all_ids = [row[0] for row in self.db.execute(stmt).all()]
        if framework_filter is None:
            return all_ids

        allowed: set[uuid.UUID] = set()
        if isinstance(framework_filter, list):
            for item in framework_filter:
                try:
                    allowed.add(item if isinstance(item, uuid.UUID) else uuid.UUID(str(item)))
                except (ValueError, TypeError):
                    continue
        return [item for item in all_ids if item in allowed]

    def _build_executive_summary(
        self,
        org_id: uuid.UUID,
        _framework_filter: list[str] | list[uuid.UUID] | dict | None,
        _date_range_days: int,
    ) -> dict:
        payload = BoardScorecardBuilder().build(org_id, self.db)
        return {
            "score": payload.get("score", 0),
            "score_delta": payload.get("score_delta"),
            "narrative": payload.get("narrative", ""),
        }

    def _build_framework_readiness(
        self,
        org_id: uuid.UUID,
        framework_filter: list[str] | list[uuid.UUID] | dict | None,
        _date_range_days: int,
    ) -> list[dict]:
        framework_ids = self._framework_ids_in_scope(org_id, framework_filter)
        results: list[dict] = []
        for framework_id in framework_ids:
            framework = self.db.get(Framework, framework_id)
            if framework is None:
                continue
            total_controls = int(
                self.db.execute(
                    select(func.count(func.distinct(ControlObligationMapping.control_id)))
                    .join(Obligation, Obligation.id == ControlObligationMapping.obligation_id)
                    .where(
                        ControlObligationMapping.organization_id == org_id,
                        ControlObligationMapping.status == "active",
                        Obligation.framework_id == framework_id,
                    )
                ).scalar_one()
            )
            implemented = int(
                self.db.execute(
                    select(func.count(func.distinct(ControlObligationMapping.control_id)))
                    .join(Obligation, Obligation.id == ControlObligationMapping.obligation_id)
                    .join(Control, Control.id == ControlObligationMapping.control_id)
                    .where(
                        ControlObligationMapping.organization_id == org_id,
                        ControlObligationMapping.status == "active",
                        Obligation.framework_id == framework_id,
                        Control.organization_id == org_id,
                        Control.status == "implemented",
                    )
                ).scalar_one()
            )
            coverage = round((implemented / total_controls) * 100.0, 2) if total_controls else 0.0
            results.append(
                {
                    "framework_id": str(framework.id),
                    "framework_name": framework.name,
                    "total_controls": total_controls,
                    "implemented_controls": implemented,
                    "coverage_pct": coverage,
                }
            )
        return results

    def _build_control_health(
        self,
        org_id: uuid.UUID,
        _framework_filter: list[str] | list[uuid.UUID] | dict | None,
        _date_range_days: int,
    ) -> dict:
        total_controls = int(
            self.db.execute(
                select(func.count(Control.id)).where(
                    Control.organization_id == org_id,
                    Control.status != "archived",
                )
            ).scalar_one()
        )

        by_status_rows = self.db.execute(
            select(Control.status, func.count(Control.id))
            .where(
                Control.organization_id == org_id,
                Control.status != "archived",
            )
            .group_by(Control.status)
        ).all()
        by_status = {str(status): int(count) for status, count in by_status_rows}

        health_avg = self.db.execute(
            select(func.avg(ScoreSnapshot.score)).where(
                ScoreSnapshot.organization_id == org_id,
                ScoreSnapshot.snapshot_type == "control_health",
            )
        ).scalar_one()
        health_score_avg = round(float(health_avg), 2) if health_avg is not None else None

        controls_needing_attention = int(
            self.db.execute(
                select(func.count(Control.id)).where(
                    Control.organization_id == org_id,
                    Control.status.in_(["at_risk", "failing"]),
                )
            ).scalar_one()
        )
        if controls_needing_attention == 0:
            controls_needing_attention = int(
                self.db.execute(
                    select(func.count(Control.id)).where(
                        Control.organization_id == org_id,
                        Control.status == "needs_review",
                    )
                ).scalar_one()
            )

        return {
            "total_controls": total_controls,
            "by_status": by_status,
            "health_score_avg": health_score_avg,
            "controls_needing_attention": controls_needing_attention,
        }

    def _build_risk_summary(
        self,
        org_id: uuid.UUID,
        _framework_filter: list[str] | list[uuid.UUID] | dict | None,
        _date_range_days: int,
    ) -> dict:
        total = int(self.db.execute(select(func.count(Risk.id)).where(Risk.organization_id == org_id)).scalar_one())
        by_severity_rows = self.db.execute(
            select(Risk.severity, func.count(Risk.id)).where(Risk.organization_id == org_id).group_by(Risk.severity)
        ).all()
        by_status_rows = self.db.execute(
            select(Risk.status, func.count(Risk.id)).where(Risk.organization_id == org_id).group_by(Risk.status)
        ).all()

        open_critical_count = int(
            self.db.execute(
                select(func.count(Risk.id)).where(
                    Risk.organization_id == org_id,
                    Risk.severity == "critical",
                    Risk.status.in_(["identified", "assessing", "treatment_planned", "in_treatment", "monitored"]),
                )
            ).scalar_one()
        )

        top_rows = self.db.execute(
            select(Risk)
            .where(
                Risk.organization_id == org_id,
                Risk.status.in_(["identified", "assessing", "treatment_planned", "in_treatment", "monitored"]),
            )
            .order_by(
                case((Risk.severity == "critical", 4), (Risk.severity == "high", 3), (Risk.severity == "medium", 2), else_=1).desc(),
                Risk.inherent_score.desc(),
            )
            .limit(5)
        ).scalars().all()

        return {
            "total": total,
            "by_severity": {str(k): int(v) for k, v in by_severity_rows},
            "by_status": {str(k): int(v) for k, v in by_status_rows},
            "open_critical_count": open_critical_count,
            "top_5_open_risks": [
                {
                    "id": str(row.id),
                    "title": row.title,
                    "severity": row.severity,
                    "status": row.status,
                    "inherent_score": row.inherent_score,
                }
                for row in top_rows
            ],
        }

    def _build_vendor_risk(
        self,
        org_id: uuid.UUID,
        _framework_filter: list[str] | list[uuid.UUID] | dict | None,
        date_range_days: int,
    ) -> dict:
        today = self._today()
        total_vendors = int(
            self.db.execute(
                select(func.count(Vendor.id)).where(
                    Vendor.organization_id == org_id,
                    Vendor.archived_at.is_(None),
                )
            ).scalar_one()
        )

        by_risk_rows = self.db.execute(
            select(Vendor.risk_tier, func.count(Vendor.id))
            .where(
                Vendor.organization_id == org_id,
                Vendor.archived_at.is_(None),
            )
            .group_by(Vendor.risk_tier)
        ).all()

        high_critical_count = int(
            self.db.execute(
                select(func.count(Vendor.id)).where(
                    Vendor.organization_id == org_id,
                    Vendor.archived_at.is_(None),
                    Vendor.risk_tier.in_(["high", "critical"]),
                )
            ).scalar_one()
        )

        assessments_due_count = int(
            self.db.execute(
                select(func.count(VendorAssessment.id)).where(
                    VendorAssessment.organization_id == org_id,
                    VendorAssessment.due_date.is_not(None),
                    VendorAssessment.due_date <= (today + timedelta(days=date_range_days)),
                    VendorAssessment.status.notin_(["completed", "cancelled", "archived"]),
                )
            ).scalar_one()
        )

        avg_questionnaire = self.db.execute(
            select(func.avg(VendorQuestionnaireResponse.calculated_risk_score)).where(
                VendorQuestionnaireResponse.organization_id == org_id,
                VendorQuestionnaireResponse.status == "completed",
                VendorQuestionnaireResponse.calculated_risk_score.is_not(None),
                VendorQuestionnaireResponse.deleted_at.is_(None),
            )
        ).scalar_one()

        return {
            "total_vendors": total_vendors,
            "by_risk_tier": {str(k): int(v) for k, v in by_risk_rows},
            "high_critical_count": high_critical_count,
            "assessments_due_count": assessments_due_count,
            "avg_questionnaire_score": round(float(avg_questionnaire), 2) if avg_questionnaire is not None else None,
        }

    def _build_evidence_status(
        self,
        org_id: uuid.UUID,
        _framework_filter: list[str] | list[uuid.UUID] | dict | None,
        date_range_days: int,
    ) -> dict:
        now = self._now()
        total_evidence = int(self.db.execute(select(func.count(EvidenceItem.id)).where(EvidenceItem.organization_id == org_id)).scalar_one())
        by_status_rows = self.db.execute(
            select(EvidenceItem.status, func.count(EvidenceItem.id)).where(EvidenceItem.organization_id == org_id).group_by(EvidenceItem.status)
        ).all()

        expiring_soon_count = int(
            self.db.execute(
                select(func.count(EvidenceItem.id)).where(
                    EvidenceItem.organization_id == org_id,
                    EvidenceItem.valid_until.is_not(None),
                    EvidenceItem.valid_until >= now,
                    EvidenceItem.valid_until <= (now + timedelta(days=date_range_days)),
                )
            ).scalar_one()
        )
        expired_count = int(
            self.db.execute(
                select(func.count(EvidenceItem.id)).where(
                    EvidenceItem.organization_id == org_id,
                    EvidenceItem.valid_until.is_not(None),
                    EvidenceItem.valid_until < now,
                )
            ).scalar_one()
        )

        active_controls = int(
            self.db.execute(
                select(func.count(Control.id)).where(
                    Control.organization_id == org_id,
                    Control.status != "archived",
                )
            ).scalar_one()
        )
        covered_controls = int(
            self.db.execute(
                select(func.count(func.distinct(EvidenceControlLink.control_id)))
                .join(EvidenceItem, EvidenceItem.id == EvidenceControlLink.evidence_item_id)
                .where(
                    EvidenceControlLink.organization_id == org_id,
                    EvidenceControlLink.link_status == "active",
                    EvidenceItem.organization_id == org_id,
                    EvidenceItem.status == "active",
                )
            ).scalar_one()
        )

        return {
            "total_evidence": total_evidence,
            "by_status": {str(k): int(v) for k, v in by_status_rows},
            "expiring_soon_count": expiring_soon_count,
            "expired_count": expired_count,
            "missing_evidence_controls_count": max(0, active_controls - covered_controls),
        }

    def _build_open_issues(
        self,
        org_id: uuid.UUID,
        _framework_filter: list[str] | list[uuid.UUID] | dict | None,
        _date_range_days: int,
    ) -> dict:
        now = self._now()
        open_stmt = (
            select(Issue)
            .where(
                Issue.organization_id == org_id,
                Issue.deleted_at.is_(None),
                Issue.status.notin_(["resolved", "closed"]),
            )
        )
        open_rows = self.db.execute(open_stmt).scalars().all()

        by_severity_rows = self.db.execute(
            select(Issue.severity, func.count(Issue.id))
            .where(
                Issue.organization_id == org_id,
                Issue.deleted_at.is_(None),
                Issue.status.notin_(["resolved", "closed"]),
            )
            .group_by(Issue.severity)
        ).all()
        by_type_rows = self.db.execute(
            select(Issue.issue_type, func.count(Issue.id))
            .where(
                Issue.organization_id == org_id,
                Issue.deleted_at.is_(None),
                Issue.status.notin_(["resolved", "closed"]),
            )
            .group_by(Issue.issue_type)
        ).all()

        sla_breached_count = int(
            self.db.execute(
                select(func.count(IssueSLATracking.id))
                .join(Issue, Issue.id == IssueSLATracking.issue_id)
                .where(
                    IssueSLATracking.organization_id == org_id,
                    (IssueSLATracking.response_breached.is_(True) | IssueSLATracking.resolution_breached.is_(True)),
                    Issue.organization_id == org_id,
                    Issue.deleted_at.is_(None),
                    Issue.status.notin_(["resolved", "closed"]),
                )
            ).scalar_one()
        )

        ages = [(now - row.created_at).total_seconds() / 86400.0 for row in open_rows]
        avg_age_days = round(sum(ages) / len(ages), 2) if ages else 0.0

        return {
            "total_open": len(open_rows),
            "by_severity": {str(k): int(v) for k, v in by_severity_rows},
            "by_type": {str(k): int(v) for k, v in by_type_rows},
            "sla_breached_count": sla_breached_count,
            "avg_age_days": avg_age_days,
        }

    def _build_policy_status(
        self,
        org_id: uuid.UUID,
        _framework_filter: list[str] | list[uuid.UUID] | dict | None,
        _date_range_days: int,
    ) -> dict:
        today = self._today()
        total_policies = int(
            self.db.execute(
                select(func.count(CompliancePolicy.id)).where(
                    CompliancePolicy.organization_id == org_id,
                    CompliancePolicy.archived_at.is_(None),
                )
            ).scalar_one()
        )

        by_status_rows = self.db.execute(
            select(CompliancePolicy.status, func.count(CompliancePolicy.id))
            .where(
                CompliancePolicy.organization_id == org_id,
                CompliancePolicy.archived_at.is_(None),
            )
            .group_by(CompliancePolicy.status)
        ).all()

        pending_review_count = int(
            self.db.execute(
                select(func.count(CompliancePolicy.id)).where(
                    CompliancePolicy.organization_id == org_id,
                    CompliancePolicy.archived_at.is_(None),
                    CompliancePolicy.review_due_date.is_not(None),
                    CompliancePolicy.review_due_date <= today,
                )
            ).scalar_one()
        )

        total_attestations = int(
            self.db.execute(
                select(func.count(PolicyAttestationRecord.id)).where(
                    PolicyAttestationRecord.organization_id == org_id,
                )
            ).scalar_one()
        )
        completed_attestations = int(
            self.db.execute(
                select(func.count(PolicyAttestationRecord.id)).where(
                    PolicyAttestationRecord.organization_id == org_id,
                    PolicyAttestationRecord.status == "attested",
                )
            ).scalar_one()
        )
        attestation_completion_rate = round((completed_attestations / total_attestations) * 100.0, 2) if total_attestations else 0.0

        policy_rows = self.db.execute(
            select(CompliancePolicy.id, CompliancePolicy.title)
            .where(
                CompliancePolicy.organization_id == org_id,
                CompliancePolicy.archived_at.is_(None),
            )
        ).all()
        policy_ids = [row[0] for row in policy_rows]
        counts = IssuePolicyLinkService(self.db).get_policy_violation_counts(org_id, policy_ids)
        top = sorted(policy_rows, key=lambda row: counts.get(row[0], 0), reverse=True)[:3]

        most_violated = [
            {
                "policy_id": str(policy_id),
                "policy_name": title,
                "violation_count": int(counts.get(policy_id, 0)),
            }
            for policy_id, title in top
        ]

        return {
            "total_policies": total_policies,
            "by_status": {str(k): int(v) for k, v in by_status_rows},
            "pending_review_count": pending_review_count,
            "attestation_completion_rate": attestation_completion_rate,
            "most_violated_policies": most_violated,
        }

    def _build_ai_governance_summary(
        self,
        org_id: uuid.UUID,
        _framework_filter: list[str] | list[uuid.UUID] | dict | None,
        _date_range_days: int,
    ) -> dict:
        try:
            total_ai_systems = int(
                self.db.execute(
                    select(func.count(AISystem.id)).where(
                        AISystem.organization_id == org_id,
                    )
                ).scalar_one()
            )
        except SQLAlchemyError:
            return {
                "status": "not_configured",
                "message": "AI Governance module not yet activated for this organization.",
            }

        if total_ai_systems == 0:
            return {
                "status": "not_configured",
                "message": "AI Governance module not yet activated for this organization.",
            }

        active = int(
            self.db.execute(
                select(func.count(AISystem.id)).where(
                    AISystem.organization_id == org_id,
                    AISystem.status == "active",
                )
            ).scalar_one()
        )
        return {
            "status": "configured",
            "total_ai_systems": total_ai_systems,
            "active_ai_systems": active,
        }

    SECTION_BUILDER_MAP = {
        "executive_summary": _build_executive_summary,
        "framework_readiness": _build_framework_readiness,
        "control_health": _build_control_health,
        "risk_summary": _build_risk_summary,
        "vendor_risk": _build_vendor_risk,
        "evidence_status": _build_evidence_status,
        "open_issues": _build_open_issues,
        "policy_status": _build_policy_status,
        "ai_governance_summary": _build_ai_governance_summary,
    }

    def generate(
        self,
        template_id: uuid.UUID,
        org_id: uuid.UUID,
        db: Session,
        created_by: uuid.UUID,
    ) -> ComplianceReport:
        _ = db
        template = self.db.execute(
            select(CustomReportTemplate).where(
                CustomReportTemplate.id == template_id,
                CustomReportTemplate.organization_id == org_id,
                CustomReportTemplate.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if template is None:
            from fastapi import HTTPException, status

            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Custom report template not found")

        result: dict = {}
        sections = list(template.sections or [])
        for section_name in sections:
            if section_name not in SECTION_NAMES:
                from fastapi import HTTPException, status

                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unsupported section: {section_name}")
            builder = self.SECTION_BUILDER_MAP[section_name]
            result[section_name] = builder(self, org_id, template.framework_filter, int(template.date_range_days))

        result["_meta"] = {
            "template_id": str(template_id),
            "template_name": template.name,
            "sections_included": sections,
            "date_range_days": int(template.date_range_days),
            "generated_at": self._now().isoformat(),
        }

        report = ComplianceReport(
            organization_id=org_id,
            report_type="custom",
            title=f"Custom Report - {template.name}",
            description="Generated from custom report template.",
            status="generated",
            framework_id=None,
            period_start=None,
            period_end=None,
            generated_by_user_id=created_by,
            generated_at=self._now(),
            content_json=result,
            content_markdown=None,
            provenance_json={
                "generated_by_user_id": str(created_by),
                "template_id": str(template_id),
                "source": "custom_report_generator",
            },
            inputs_summary_json=result,
        )
        self.db.add(report)
        self.db.flush()
        return report
