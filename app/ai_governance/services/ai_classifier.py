import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai_risk_classification import AIRiskClassification
from app.models.ai_system import AISystem


CLASSIFICATION_TREE = {
    "root": {
        "question": "Does the system deploy in critical infrastructure (energy, water, transport, finance)?",
        "key": "critical_infrastructure",
        "yes": "high",
        "no": "check_employment",
    },
    "check_employment": {
        "question": "Does the system affect employment, worker management, or hiring decisions?",
        "key": "employment_decisions",
        "yes": "high",
        "no": "check_biometric",
    },
    "check_biometric": {
        "question": "Does the system process biometric data for identification?",
        "key": "biometric_data",
        "yes": "high",
        "no": "check_essential_services",
    },
    "check_essential_services": {
        "question": "Does the system affect access to essential services (healthcare, education, benefits)?",
        "key": "essential_services",
        "yes": "high",
        "no": "check_law_enforcement",
    },
    "check_law_enforcement": {
        "question": "Is the system used by or for law enforcement, migration, or border control?",
        "key": "law_enforcement",
        "yes": "high",
        "no": "check_manipulation",
    },
    "check_manipulation": {
        "question": "Could the system manipulate human behavior, exploit vulnerabilities, or use subliminal techniques?",
        "key": "manipulation",
        "yes": "prohibited",
        "no": "check_social_scoring",
    },
    "check_social_scoring": {
        "question": "Does the system perform social scoring or general-purpose citizen evaluation?",
        "key": "social_scoring",
        "yes": "prohibited",
        "no": "check_realtime_biometric",
    },
    "check_realtime_biometric": {
        "question": "Does the system perform real-time remote biometric identification in public spaces?",
        "key": "realtime_biometric_public",
        "yes": "prohibited",
        "no": "check_transparency",
    },
    "check_transparency": {
        "question": "Does the system interact with humans and could be mistaken for a human?",
        "key": "transparency_obligation",
        "yes": "limited",
        "no": "minimal",
    },
}

MANDATORY_CONTROLS = {
    "prohibited": [
        "Immediately decommission or redesign the system",
        "Legal review required before any further deployment",
        "Document prohibition basis under EU AI Act Article 5",
    ],
    "high": [
        "Conformity assessment required",
        "Technical documentation must be completed",
        "Human oversight mechanism must be implemented",
        "Registration in EU AI Act database required",
        "Post-market monitoring plan required",
    ],
    "limited": [
        "Transparency disclosure to users required",
        "Labeling as AI-generated content required if applicable",
    ],
    "minimal": [
        "Voluntary codes of conduct recommended",
        "Internal documentation encouraged",
    ],
}


class AIRiskClassifier:
    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _normalize_answer(self, value: str | None) -> str:
        if value is None:
            return "no"
        v = str(value).strip().lower()
        if v not in {"yes", "no"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Answers must be 'yes' or 'no'")
        return v

    def _walk_tree(self, answers: dict) -> str:
        node_key = "root"
        while True:
            node = CLASSIFICATION_TREE[node_key]
            answer = self._normalize_answer(answers.get(node["key"]))
            next_node = node[answer]
            if next_node in {"prohibited", "high", "limited", "minimal"}:
                return next_node
            node_key = str(next_node)

    def _get_path(self, answers: dict) -> list[dict[str, str]]:
        path: list[dict[str, str]] = []
        node_key = "root"
        while True:
            node = CLASSIFICATION_TREE[node_key]
            answer = self._normalize_answer(answers.get(node["key"]))
            next_node = node[answer]
            path.append({"node": node_key, "key": node["key"], "answer": answer, "next": str(next_node)})
            if next_node in {"prohibited", "high", "limited", "minimal"}:
                break
            node_key = str(next_node)
        return path

    def _upsert(
        self,
        *,
        org_id: uuid.UUID,
        system_id: uuid.UUID,
        tier: str,
        method: str,
        basis: dict,
        classified_by: uuid.UUID,
        db: Session,
    ) -> AIRiskClassification:
        existing = db.execute(
            select(AIRiskClassification).where(
                AIRiskClassification.organization_id == org_id,
                AIRiskClassification.ai_system_id == system_id,
            )
        ).scalar_one_or_none()

        now = self.utcnow()
        if existing is None:
            result = AIRiskClassification(
                organization_id=org_id,
                ai_system_id=system_id,
                risk_tier=tier,
                classification_method=method,
                classification_basis=basis,
                classified_by=classified_by,
                classified_at=now,
                updated_at=now,
            )
            db.add(result)
            db.flush()
        else:
            existing.risk_tier = tier
            existing.classification_method = method
            existing.classification_basis = basis
            existing.classified_by = classified_by
            existing.classified_at = now
            existing.updated_at = now
            result = existing

        system = db.execute(
            select(AISystem).where(
                AISystem.id == system_id,
                AISystem.organization_id == org_id,
                AISystem.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if system is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="AI system not found")
        system.risk_tier = tier

        if tier in {"high", "prohibited"}:
            result.review_required_at = now + timedelta(days=180)
        else:
            result.review_required_at = None
        db.flush()
        return result

    def classify_guided(
        self,
        system_id: uuid.UUID,
        answers: dict,
        classified_by: uuid.UUID,
        org_id: uuid.UUID,
        db: Session,
    ) -> AIRiskClassification:
        tier = self._walk_tree(answers)
        basis = {
            "method": "guided",
            "answers": answers,
            "decision_path": self._get_path(answers),
            "mandatory_controls": MANDATORY_CONTROLS[tier],
        }
        return self._upsert(
            org_id=org_id,
            system_id=system_id,
            tier=tier,
            method="guided",
            basis=basis,
            classified_by=classified_by,
            db=db,
        )

    def classify_manual(
        self,
        system_id: uuid.UUID,
        risk_tier: str,
        classified_by: uuid.UUID,
        org_id: uuid.UUID,
        db: Session,
        basis_notes: str | None = None,
    ) -> AIRiskClassification:
        if risk_tier not in {"prohibited", "high", "limited", "minimal"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid risk_tier")
        basis = {
            "method": "manual",
            "notes": basis_notes,
            "mandatory_controls": MANDATORY_CONTROLS[risk_tier],
        }
        return self._upsert(
            org_id=org_id,
            system_id=system_id,
            tier=risk_tier,
            method="manual",
            basis=basis,
            classified_by=classified_by,
            db=db,
        )

    def get_classification_questions(self) -> list[dict[str, str]]:
        ordered = [
            "root",
            "check_employment",
            "check_biometric",
            "check_essential_services",
            "check_law_enforcement",
            "check_manipulation",
            "check_social_scoring",
            "check_realtime_biometric",
            "check_transparency",
        ]
        return [{"key": CLASSIFICATION_TREE[node]["key"], "question": CLASSIFICATION_TREE[node]["question"]} for node in ordered]
