import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_governance.schemas.ai_classification import AIRiskClassificationRead, EUAIActClassifyRequest
from app.ai_governance.services.ai_classifier import AIRiskClassifier, MANDATORY_CONTROLS
from app.ai_governance.services.ai_governance_event_service import AIGovernanceEventService
from app.ai_governance.services.eu_act_classification_service import EUAIActClassificationService
from app.models.ai_risk_classification import AIRiskClassification
from app.models.ai_system import AISystem
from app.services.audit_service import AuditService

# Human-readable phrasing for each guided-classification question key, used to
# explain *why* a tier was assigned instead of surfacing a bare "yes"/"no".
QUESTION_EXPLANATIONS = {
    "critical_infrastructure": "it deploys in critical infrastructure (energy, water, transport, finance)",
    "employment_decisions": "it affects employment, worker management, or hiring decisions",
    "biometric_data": "it processes biometric data for identification",
    "essential_services": "it affects access to essential services (healthcare, education, benefits)",
    "law_enforcement": "it is used by or for law enforcement, migration, or border control",
    "manipulation": "it could manipulate human behavior, exploit vulnerabilities, or use subliminal techniques",
    "social_scoring": "it performs social scoring or general-purpose citizen evaluation",
    "realtime_biometric_public": "it performs real-time remote biometric identification in public spaces",
    "transparency_obligation": "it interacts with humans and could be mistaken for a human",
}

# The guided/manual risk-tier vocabulary ("prohibited", "high", "limited",
# "minimal") is coarser than the formal EU AI Act classification's
# article_category vocabulary. "high" is mapped to Annex III (the
# high-risk use-case categories the guided questionnaire actually probes
# for -- critical infrastructure, employment, biometric data, essential
# services, law enforcement) rather than Annex I, since the guided flow
# never asks about products already regulated under EU harmonization
# legislation (Annex I's basis).
RISK_TIER_TO_ARTICLE_CATEGORY = {
    "prohibited": "prohibited",
    "high": "high_risk_annex3",
    "limited": "limited_risk",
    "minimal": "minimal_risk",
}


class AIRiskClassificationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.classifier = AIRiskClassifier()

    def _sync_eu_act_classification(self, org_id: uuid.UUID, system_id: uuid.UUID, risk_tier: str, user_id: uuid.UUID) -> None:
        """Write the guided/manual risk-tier decision through to the formal
        EU AI Act classification store, so `/eu-act-obligations` reflects a
        completed guided or manual classification without requiring a
        separate, redundant submission through `/eu-act-classification`.
        """
        article_category = RISK_TIER_TO_ARTICLE_CATEGORY.get(risk_tier)
        if article_category is None:
            return
        EUAIActClassificationService(self.db).classify_system(
            org_id,
            system_id,
            EUAIActClassifyRequest(article_category=article_category),
            user_id,
        )

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
        self._sync_eu_act_classification(org_id, system_id, row.risk_tier, user_id)
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
        self._sync_eu_act_classification(org_id, system_id, row.risk_tier, user_id)
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

    def build_classification_explanation(self, row: AIRiskClassification) -> str | None:
        basis = row.classification_basis or {}
        method = basis.get("method")

        if method == "manual":
            notes = basis.get("notes")
            if notes:
                return f"Manually classified as {row.risk_tier} based on: {notes}"
            return f"Manually classified as {row.risk_tier} with no basis notes provided."

        if method == "guided":
            decision_path = basis.get("decision_path") or []
            # The tier-determining step is the last "yes" answer in the walked
            # path (a "no" all the way through lands on minimal/limited).
            triggering_steps = [step for step in decision_path if step.get("answer") == "yes"]
            if triggering_steps:
                last = triggering_steps[-1]
                reason = QUESTION_EXPLANATIONS.get(last.get("key"), last.get("key"))
                return f"Classified {row.risk_tier}-risk because {reason}."
            return f"Classified {row.risk_tier}-risk: none of the guided questionnaire's triggering criteria were answered 'yes'."

        return None

    def to_read(self, org_id: uuid.UUID, row: AIRiskClassification) -> AIRiskClassificationRead:
        system = self.db.execute(
            select(AISystem).where(
                AISystem.organization_id == org_id,
                AISystem.id == row.ai_system_id,
            )
        ).scalar_one_or_none()

        reassessment_required = bool(
            system is not None
            and system.updated_at is not None
            and row.classified_at is not None
            and system.updated_at > row.classified_at
        )

        data = AIRiskClassificationRead.model_validate(row).model_dump()
        data["classification_explanation"] = self.build_classification_explanation(row)
        data["reassessment_required"] = reassessment_required
        return AIRiskClassificationRead(**data)
