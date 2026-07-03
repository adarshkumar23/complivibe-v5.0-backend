from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai_bias_assessment import AIBiasAssessment
from app.models.ai_system import AISystem
from app.models.aibom_component import AIBOMComponent
from app.models.aibom_record import AIBOMRecord
from app.models.issue import Issue
from app.models.model_card import ModelCard
from app.schemas.issue import IssueCreate
from app.services.audit_service import AuditService

ATLAS_TACTICS = [
    "ATLAS-RECON",
    "ATLAS-RD",
    "ATLAS-IA",
    "ATLAS-ML-ATK",
    "ATLAS-EXFIL",
    "ATLAS-IMPACT",
]


class AIDepthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _verify_system_ownership(self, org_id: uuid.UUID, system_id: uuid.UUID) -> AISystem:
        system = self.db.execute(
            select(AISystem).where(
                AISystem.id == system_id,
                AISystem.organization_id == org_id,
                AISystem.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if system is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system not found")
        return system

    def submit_bias_assessment(
        self,
        org_id: uuid.UUID,
        system_id: uuid.UUID,
        data,
        assessed_by: uuid.UUID,
    ) -> AIBiasAssessment:
        self._verify_system_ownership(org_id, system_id)

        passed = data.metric_value <= data.threshold_value if data.lower_is_better else data.metric_value >= data.threshold_value
        now = self.utcnow()
        assessment = AIBiasAssessment(
            organization_id=org_id,
            system_id=system_id,
            assessment_method=data.assessment_method,
            protected_attribute=data.protected_attribute,
            metric_name=data.metric_name,
            metric_value=data.metric_value,
            threshold_value=data.threshold_value,
            passed=passed,
            remediation_notes=data.remediation_notes,
            assessed_by=assessed_by,
            assessed_at=now,
            created_at=now,
        )
        self.db.add(assessment)
        self.db.flush()

        system = self.db.get(AISystem, system_id)
        if system is not None:
            system.bias_assessment_status = "completed" if assessment.passed else "remediation_needed"
            system.last_bias_assessment_at = now
            self.db.flush()

        if not assessment.passed:
            from app.compliance.services.issue_service import IssueService

            IssueService(self.db).create_issue(
                org_id=org_id,
                data=IssueCreate(
                    title=f"Bias Detected in AI System: {data.protected_attribute} ({data.metric_name})",
                    description=(
                        "Bias assessment failed.\n"
                        f"Method: {data.assessment_method}\n"
                        f"Protected attribute: {data.protected_attribute}\n"
                        f"Metric: {data.metric_name} = {data.metric_value:.4f} (threshold: {data.threshold_value})\n"
                        f"Remediation: {data.remediation_notes or 'See AI team'}"
                    ),
                    issue_type="custom",
                    severity="high",
                    source_type="monitoring_alert",
                    owner_id=assessed_by,
                    assigned_to=assessed_by,
                ),
                created_by=assessed_by,
            )

        AuditService(self.db).write_audit_log(
            action="ai.bias_assessment_submitted",
            entity_type="ai_bias_assessments",
            organization_id=org_id,
            actor_user_id=assessed_by,
            entity_id=assessment.id,
            metadata_json={
                "passed": assessment.passed,
                "metric": data.metric_name,
                "protected_attribute": data.protected_attribute,
            },
        )
        return assessment

    def get_bias_history(
        self,
        org_id: uuid.UUID,
        system_id: uuid.UUID,
    ) -> list[AIBiasAssessment]:
        self._verify_system_ownership(org_id, system_id)
        return (
            self.db.execute(
                select(AIBiasAssessment)
                .where(
                    AIBiasAssessment.system_id == system_id,
                    AIBiasAssessment.organization_id == org_id,
                )
                .order_by(AIBiasAssessment.assessed_at.desc())
            )
            .scalars()
            .all()
        )

    def update_human_oversight(
        self,
        org_id: uuid.UUID,
        system_id: uuid.UUID,
        oversight_level: str,
        explainability_method: str | None,
        user_id: uuid.UUID,
    ) -> AISystem:
        system = self._verify_system_ownership(org_id, system_id)
        system.human_oversight_level = oversight_level
        if explainability_method:
            system.explainability_method = explainability_method
        self.db.flush()

        if oversight_level == "full_automation" and (system.risk_tier or "") in ("high", "unacceptable"):
            from app.compliance.services.issue_service import IssueService

            IssueService(self.db).create_issue(
                org_id=org_id,
                data=IssueCreate(
                    title=f"High-Risk AI System Without Human Oversight: {system.name}",
                    description=(
                        "EU AI Act Art. 14 requires human oversight for high-risk AI systems. "
                        f"This system is classified as '{oversight_level}' which may not satisfy Art. 14 requirements."
                    ),
                    issue_type="custom",
                    severity="critical",
                    source_type="monitoring_alert",
                    owner_id=user_id,
                    assigned_to=user_id,
                ),
                created_by=user_id,
            )

        AuditService(self.db).write_audit_log(
            action="ai.oversight_level_updated",
            entity_type="ai_systems",
            organization_id=org_id,
            actor_user_id=user_id,
            entity_id=system_id,
            metadata_json={
                "oversight_level": oversight_level,
                "explainability_method": explainability_method,
            },
        )
        return system

    def compute_data_governance_score(self, org_id: uuid.UUID, system_id: uuid.UUID) -> dict:
        system = self._verify_system_ownership(org_id, system_id)

        score_components: dict[str, float] = {}

        aibom = self.db.execute(
            select(AIBOMRecord)
            .where(
                AIBOMRecord.organization_id == org_id,
                AIBOMRecord.ai_system_id == system_id,
            )
            .order_by(AIBOMRecord.version.desc())
        ).scalars().first()
        has_aibom = aibom is not None
        has_training_data = False
        if aibom is not None:
            training_components = self.db.execute(
                select(AIBOMComponent)
                .where(
                    AIBOMComponent.organization_id == org_id,
                    AIBOMComponent.aibom_id == aibom.id,
                    AIBOMComponent.component_type == "training_data",
                )
            ).scalars().all()
            has_training_data = len(training_components) > 0

        score_components["aibom"] = 1.0 if has_training_data else 0.5 if has_aibom else 0.0

        published_card = self.db.execute(
            select(ModelCard).where(
                ModelCard.organization_id == org_id,
                ModelCard.ai_system_id == system_id,
                ModelCard.status == "published",
            )
        ).scalar_one_or_none()
        score_components["model_card"] = 1.0 if published_card else 0.0

        score_components["oversight"] = (
            1.0
            if system.human_oversight_level and system.human_oversight_level != "full_automation"
            else 0.3 if system.human_oversight_level else 0.0
        )

        bias_done = self.db.execute(
            select(AIBiasAssessment.id).where(
                AIBiasAssessment.organization_id == org_id,
                AIBiasAssessment.system_id == system_id,
            )
        ).all()
        score_components["bias_assessment"] = 1.0 if len(bias_done) > 0 else 0.0

        score_components["threat_assessment"] = 1.0 if system.atlas_risk_score is not None else 0.0

        total_score = sum(score_components.values()) / max(len(score_components), 1)
        system.data_governance_score = total_score
        self.db.flush()

        grade = (
            "A"
            if total_score >= 0.90
            else "B" if total_score >= 0.75 else "C" if total_score >= 0.60 else "D" if total_score >= 0.40 else "F"
        )

        return {
            "system_id": str(system_id),
            "system_name": system.name,
            "total_score": round(total_score, 4),
            "components": score_components,
            "grade": grade,
            "computed_at": self.utcnow().isoformat(),
        }

    def get_ai_governance_scorecard(self, org_id: uuid.UUID) -> dict:
        systems = (
            self.db.execute(
                select(AISystem).where(
                    AISystem.organization_id == org_id,
                    AISystem.deleted_at.is_(None),
                )
            )
            .scalars()
            .all()
        )

        if not systems:
            return {
                "org_id": str(org_id),
                "total_systems": 0,
                "scorecard": {},
            }

        total = len(systems)
        with_scores = sum(1 for s in systems if s.data_governance_score is not None)
        bias_assessed = sum(1 for s in systems if s.bias_assessment_status in ("completed", "remediation_needed"))
        oversight_set = sum(1 for s in systems if s.human_oversight_level is not None)
        high_risk_no_oversight = sum(
            1
            for s in systems
            if (s.risk_tier or "") in ("high", "unacceptable") and s.human_oversight_level == "full_automation"
        )
        avg_score = (
            sum(float(s.data_governance_score) for s in systems if s.data_governance_score is not None) / max(with_scores, 1)
        )

        return {
            "org_id": str(org_id),
            "total_systems": total,
            "scorecard": {
                "avg_governance_score": round(avg_score, 4),
                "bias_assessment_coverage": round(bias_assessed / total, 4),
                "oversight_level_set": round(oversight_set / total, 4),
                "high_risk_no_oversight_count": high_risk_no_oversight,
                "with_governance_score": with_scores,
            },
            "alerts": [
                f"{high_risk_no_oversight} high-risk system(s) lack human oversight"
            ]
            if high_risk_no_oversight > 0
            else [],
        }

    def get_issue_count_for_system(self, org_id: uuid.UUID, system_id: uuid.UUID, issue_type: str | None = None) -> int:
        stmt = select(Issue).where(
            Issue.organization_id == org_id,
            Issue.deleted_at.is_(None),
        )
        if issue_type is not None:
            stmt = stmt.where(Issue.issue_type == issue_type)
        rows = self.db.execute(stmt).scalars().all()
        marker = str(system_id)
        return sum(1 for row in rows if marker in (row.title or "") or marker in (row.description or ""))
