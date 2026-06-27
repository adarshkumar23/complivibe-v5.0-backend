import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_governance.services.ai_classifier import AIRiskClassifier, MANDATORY_CONTROLS
from app.ai_governance.services.ai_governance_event_service import AIGovernanceEventService
from app.models.ai_risk_classification import AIRiskClassification
from app.models.ai_system import AISystem
from app.services.audit_service import AuditService


class AIRiskClassificationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.classifier = AIRiskClassifier()

    def _require_system(self, org_id: uuid.UUID, system_id: uuid.UUID) -> AISystem:
        row = self.db.execute(
            select(AISystem).where(
                AISystem.id == system_id,
                AISystem.organization_id == org_id,
                AISystem.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system not found")
        return row

    def start_guided_classification(self, org_id: uuid.UUID, system_id: uuid.UUID, _data, user_id: uuid.UUID) -> dict:
        self._require_system(org_id, system_id)
        _ = user_id
        return {"questions": self.classifier.get_classification_questions()}

    def submit_guided_answers(self, org_id: uuid.UUID, system_id: uuid.UUID, answers: dict, user_id: uuid.UUID) -> AIRiskClassification:
        self._require_system(org_id, system_id)
        row = self.classifier.classify_guided(
            system_id=system_id,
            answers=answers,
            classified_by=user_id,
            org_id=org_id,
            db=self.db,
        )
        AIGovernanceEventService.log(
            self.db,
            org_id,
            "classification.updated",
            actor_id=user_id,
            actor_type="user",
            ai_system_id=system_id,
            event_data={"method": "guided", "risk_tier": row.risk_tier},
        )
        AuditService(self.db).write_audit_log(
            action="classification.updated",
            entity_type="ai_risk_classification",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"risk_tier": row.risk_tier, "classification_method": row.classification_method},
            metadata_json={"source": "api"},
        )
        return row

    def manual_classify(
        self,
        org_id: uuid.UUID,
        system_id: uuid.UUID,
        risk_tier: str,
        notes: str | None,
        user_id: uuid.UUID,
    ) -> AIRiskClassification:
        self._require_system(org_id, system_id)
        row = self.classifier.classify_manual(
            system_id=system_id,
            risk_tier=risk_tier,
            classified_by=user_id,
            org_id=org_id,
            db=self.db,
            basis_notes=notes,
        )
        AIGovernanceEventService.log(
            self.db,
            org_id,
            "classification.updated",
            actor_id=user_id,
            actor_type="user",
            ai_system_id=system_id,
            event_data={"method": "manual", "risk_tier": row.risk_tier},
        )
        AuditService(self.db).write_audit_log(
            action="classification.updated",
            entity_type="ai_risk_classification",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"risk_tier": row.risk_tier, "classification_method": row.classification_method},
            metadata_json={"source": "api"},
        )
        return row

    def get_classification(self, org_id: uuid.UUID, system_id: uuid.UUID) -> AIRiskClassification:
        row = self.db.execute(
            select(AIRiskClassification).where(
                AIRiskClassification.organization_id == org_id,
                AIRiskClassification.ai_system_id == system_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI risk classification not found")
        return row

    def get_mandatory_controls(self, org_id: uuid.UUID, system_id: uuid.UUID) -> list[str]:
        row = self.get_classification(org_id, system_id)
        return list(MANDATORY_CONTROLS.get(row.risk_tier, []))
