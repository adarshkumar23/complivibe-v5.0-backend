import uuid
from collections import Counter
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.compliance.services.questionnaire_template_service import QuestionnaireTemplateService
from app.models.ai_vendor_assessment import AIVendorAssessment
from app.models.questionnaire_template import QuestionnaireTemplate
from app.models.vendor import Vendor
from app.services.audit_service import AuditService
from app.services.seed_service import SeedService


class AIVendorAssessmentService:
    AI_VENDOR_TEMPLATE_NAME = "AI Vendor Governance Assessment"

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _require_vendor(self, org_id: uuid.UUID, vendor_id: uuid.UUID) -> Vendor:
        row = self.db.execute(
            select(Vendor).where(
                Vendor.id == vendor_id,
                Vendor.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")
        return row

    def _require_assessment(self, org_id: uuid.UUID, assessment_id: uuid.UUID) -> AIVendorAssessment:
        row = self.db.execute(
            select(AIVendorAssessment).where(
                AIVendorAssessment.id == assessment_id,
                AIVendorAssessment.organization_id == org_id,
                AIVendorAssessment.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI vendor assessment not found")
        return row

    def create_assessment(self, org_id: uuid.UUID, vendor_id: uuid.UUID, data, assessor_id: uuid.UUID) -> AIVendorAssessment:
        self._require_vendor(org_id, vendor_id)

        row = AIVendorAssessment(
            organization_id=org_id,
            vendor_id=vendor_id,
            assessor_id=assessor_id,
            status="draft",
            ai_model_name=data.ai_model_name,
            ai_model_version=data.ai_model_version,
            ai_model_provider=data.ai_model_provider,
            model_type=data.model_type,
            training_data_source=data.training_data_source,
            training_data_governance=data.training_data_governance,
            data_exits_environment=data.data_exits_environment,
            data_exits_details=data.data_exits_details,
            bias_testing_performed=data.bias_testing_performed,
            bias_testing_method=data.bias_testing_method,
            bias_testing_frequency=data.bias_testing_frequency,
            explainability_approach=data.explainability_approach,
            human_oversight_required=data.human_oversight_required,
            human_oversight_details=data.human_oversight_details,
            output_used_for_decisions=data.output_used_for_decisions,
            decision_types=data.decision_types,
            regulatory_obligations=data.regulatory_obligations,
            vendor_ai_policy_url=data.vendor_ai_policy_url,
            incident_history=data.incident_history,
            assessor_notes=data.assessor_notes,
        )
        self.db.add(row)
        self.db.flush()

        SeedService.ensure_questionnaire_templates(self.db)
        template = self.db.execute(
            select(QuestionnaireTemplate).where(
                QuestionnaireTemplate.organization_id.is_(None),
                QuestionnaireTemplate.is_system_template.is_(True),
                QuestionnaireTemplate.is_active.is_(True),
                QuestionnaireTemplate.name == self.AI_VENDOR_TEMPLATE_NAME,
                QuestionnaireTemplate.deleted_at.is_(None),
            )
        ).scalar_one_or_none()

        if template is not None:
            response_payload = SimpleNamespace(
                title=f"{self.AI_VENDOR_TEMPLATE_NAME} - {row.id}",
                due_date=None,
            )
            response = QuestionnaireTemplateService(self.db).create_response(
                org_id,
                vendor_id,
                template.id,
                response_payload,
                assessor_id,
            )
            self.db.flush()

            AuditService(self.db).write_audit_log(
                action="ai_vendor_assessment.template_auto_applied",
                entity_type="ai_vendor_assessment",
                entity_id=row.id,
                organization_id=org_id,
                actor_user_id=assessor_id,
                after_json={
                    "template_id": str(template.id),
                    "template_name": template.name,
                    "questionnaire_response_id": str(response.id),
                },
                metadata_json={"source": "service_hook"},
            )

        AuditService(self.db).write_audit_log(
            action="ai_vendor_assessment.created",
            entity_type="ai_vendor_assessment",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=assessor_id,
            after_json={"vendor_id": str(row.vendor_id), "status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def get_assessment(self, org_id: uuid.UUID, assessment_id: uuid.UUID) -> AIVendorAssessment:
        return self._require_assessment(org_id, assessment_id)

    def list_assessments(
        self,
        org_id: uuid.UUID,
        *,
        vendor_id: uuid.UUID | None = None,
        status_value: str | None = None,
        risk_level: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[AIVendorAssessment]:
        stmt = select(AIVendorAssessment).where(
            AIVendorAssessment.organization_id == org_id,
            AIVendorAssessment.deleted_at.is_(None),
        )
        if vendor_id is not None:
            stmt = stmt.where(AIVendorAssessment.vendor_id == vendor_id)
        if status_value is not None:
            stmt = stmt.where(AIVendorAssessment.status == status_value)
        if risk_level is not None:
            stmt = stmt.where(AIVendorAssessment.overall_risk_level == risk_level)

        return self.db.execute(stmt.order_by(AIVendorAssessment.created_at.desc()).offset(skip).limit(limit)).scalars().all()

    def update_assessment(self, org_id: uuid.UUID, assessment_id: uuid.UUID, data, actor_user_id: uuid.UUID) -> AIVendorAssessment:
        row = self._require_assessment(org_id, assessment_id)
        if row.status in {"completed", "archived"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Completed/archived assessments are immutable")

        updates = data.model_dump(exclude_unset=True)
        if "status" in updates and updates["status"] == "completed":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Use complete endpoint to finalize assessment")

        before = {"status": row.status, "risk_score": row.risk_score, "overall_risk_level": row.overall_risk_level}
        for key, value in updates.items():
            setattr(row, key, value)

        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="ai_vendor_assessment.updated",
            entity_type="ai_vendor_assessment",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json={"status": row.status, "risk_score": row.risk_score, "overall_risk_level": row.overall_risk_level},
            metadata_json={"source": "api"},
        )
        return row

    @staticmethod
    def _compute_risk_score(row: AIVendorAssessment) -> tuple[int, str]:
        score = 0

        if row.data_exits_environment is True:
            score += 30
        elif row.data_exits_environment is False:
            score -= 10

        if row.bias_testing_performed is False:
            score += 20
        elif row.bias_testing_performed is True:
            score -= 10

        if row.human_oversight_required is False and row.output_used_for_decisions is True:
            score += 25
        elif row.human_oversight_required is True:
            score -= 10

        if row.training_data_governance is None:
            score += 15
        if row.explainability_approach is None:
            score += 10

        obligations = row.regulatory_obligations if isinstance(row.regulatory_obligations, list) else []
        score += min(len(obligations) * 5, 20)

        score = max(0, min(100, int(score)))

        if score <= 25:
            level = "low"
        elif score <= 50:
            level = "medium"
        elif score <= 75:
            level = "high"
        else:
            level = "critical"

        return score, level

    def complete_assessment(self, org_id: uuid.UUID, assessment_id: uuid.UUID, user_id: uuid.UUID) -> AIVendorAssessment:
        row = self._require_assessment(org_id, assessment_id)
        if row.status == "archived":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Archived assessments cannot be completed")

        score, level = self._compute_risk_score(row)
        row.risk_score = score
        row.overall_risk_level = level
        row.status = "completed"
        row.completed_at = self.utcnow()

        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="ai_vendor_assessment.completed",
            entity_type="ai_vendor_assessment",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status, "risk_score": row.risk_score, "overall_risk_level": row.overall_risk_level},
            metadata_json={"source": "api"},
        )
        return row

    def get_ai_risk_summary(self, org_id: uuid.UUID) -> dict:
        rows = self.db.execute(
            select(AIVendorAssessment).where(
                AIVendorAssessment.organization_id == org_id,
                AIVendorAssessment.deleted_at.is_(None),
            )
        ).scalars().all()

        by_status = Counter(row.status for row in rows)
        by_risk_level = Counter((row.overall_risk_level or "unscored") for row in rows)
        by_model_type = Counter((row.model_type or "unknown") for row in rows)

        return {
            "total_assessments": len(rows),
            "by_status": {k: int(v) for k, v in by_status.items()},
            "by_risk_level": {k: int(v) for k, v in by_risk_level.items()},
            "by_model_type": {k: int(v) for k, v in by_model_type.items()},
            "critical_count": int(by_risk_level.get("critical", 0)),
            "data_exits_count": int(sum(1 for row in rows if row.data_exits_environment is True)),
            "no_bias_testing_count": int(sum(1 for row in rows if row.bias_testing_performed is False)),
            "no_human_oversight_decisions_count": int(
                sum(1 for row in rows if row.human_oversight_required is False and row.output_used_for_decisions is True)
            ),
        }

    def soft_delete_assessment(self, org_id: uuid.UUID, assessment_id: uuid.UUID, user_id: uuid.UUID) -> AIVendorAssessment:
        row = self._require_assessment(org_id, assessment_id)
        if row.status != "draft":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only draft assessments can be deleted")

        row.deleted_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="ai_vendor_assessment.deleted",
            entity_type="ai_vendor_assessment",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"deleted_at": row.deleted_at.isoformat() if row.deleted_at else None},
            metadata_json={"source": "api"},
        )
        return row
