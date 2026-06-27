import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_governance.services.ai_governance_event_service import AIGovernanceEventService
from app.ai_governance.services.ai_recommendation_engine import CAVEAT, AIRecommendationEngine
from app.models.ai_risk_assessment import AIRiskAssessment
from app.models.ai_risk_recommendation import AIRiskRecommendation
from app.models.ai_system import AISystem
from app.models.task import Task
from app.services.audit_service import AuditService

ALLOWED_SOURCE_TYPES = {"risk_assessment", "monitoring_breach", "signal", "manual"}
ALLOWED_RECOMMENDATION_CATEGORY = {"technical_control", "process_control", "documentation", "audit", "decommission"}
ALLOWED_PRIORITY = {"critical", "high", "medium", "low"}
ALLOWED_STATUS = {"active", "applied", "dismissed"}


class AIRecommendationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.engine = AIRecommendationEngine()

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _require_system(self, org_id: uuid.UUID, system_id: uuid.UUID) -> AISystem:
        row = self.db.execute(
            select(AISystem).where(
                AISystem.organization_id == org_id,
                AISystem.id == system_id,
                AISystem.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system not found")
        return row

    def _require_recommendation(self, org_id: uuid.UUID, rec_id: uuid.UUID) -> AIRiskRecommendation:
        row = self.db.execute(
            select(AIRiskRecommendation).where(
                AIRiskRecommendation.organization_id == org_id,
                AIRiskRecommendation.id == rec_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI risk recommendation not found")
        return row

    @staticmethod
    def _priority_from_text(text: str) -> str:
        lower = text.lower()
        if any(token in lower for token in ["immediately", "halt", "suspend", "incident", "72 hours"]):
            return "critical"
        if any(token in lower for token in ["within 14 days", "within 30 days", "high-stakes", "audit"]):
            return "high"
        if any(token in lower for token in ["next periodic", "schedule"]):
            return "medium"
        return "low"

    @staticmethod
    def _category_from_text(text: str) -> str:
        lower = text.lower()
        if any(token in lower for token in ["monitoring", "testing", "access controls", "isolate", "layer"]):
            return "technical_control"
        if any(token in lower for token in ["document", "dpia", "criteria", "notification"]):
            return "documentation"
        if any(token in lower for token in ["audit", "third party", "independent"]):
            return "audit"
        if any(token in lower for token in ["halt deployment", "suspend"]):
            return "decommission"
        return "process_control"

    def _latest_completed_assessment(self, org_id: uuid.UUID, system_id: uuid.UUID) -> AIRiskAssessment | None:
        return self.db.execute(
            select(AIRiskAssessment)
            .where(
                AIRiskAssessment.organization_id == org_id,
                AIRiskAssessment.ai_system_id == system_id,
                AIRiskAssessment.status == "completed",
            )
            .order_by(AIRiskAssessment.completed_at.desc(), AIRiskAssessment.created_at.desc())
        ).scalars().first()

    def generate_recommendations(
        self,
        org_id: uuid.UUID,
        system_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[AIRiskRecommendation]:
        self._require_system(org_id, system_id)
        texts = self.engine.generate(org_id, system_id, self.db)
        source_assessment = self._latest_completed_assessment(org_id, system_id)

        created_rows: list[AIRiskRecommendation] = []
        now = self.utcnow()
        for text in texts:
            existing_active = self.db.execute(
                select(AIRiskRecommendation).where(
                    AIRiskRecommendation.organization_id == org_id,
                    AIRiskRecommendation.ai_system_id == system_id,
                    AIRiskRecommendation.recommendation_text == text,
                    AIRiskRecommendation.status == "active",
                )
            ).scalar_one_or_none()
            if existing_active is not None:
                continue

            row = AIRiskRecommendation(
                organization_id=org_id,
                ai_system_id=system_id,
                source_type="risk_assessment" if source_assessment else "manual",
                recommendation_text=text,
                recommendation_category=self._category_from_text(text),
                priority=self._priority_from_text(text),
                status="active",
                source_ref_id=source_assessment.id if source_assessment else None,
                created_at=now,
                updated_at=now,
            )
            self.db.add(row)
            self.db.flush()
            created_rows.append(row)

            AIGovernanceEventService.log(
                self.db,
                org_id,
                "recommendation.generated",
                actor_id=user_id,
                actor_type="user",
                ai_system_id=system_id,
                event_data={"recommendation_id": str(row.id), "source_type": row.source_type},
            )
            AuditService(self.db).write_audit_log(
                action="recommendation.generated",
                entity_type="ai_risk_recommendation",
                entity_id=row.id,
                organization_id=org_id,
                actor_user_id=user_id,
                after_json={
                    "ai_system_id": str(row.ai_system_id),
                    "priority": row.priority,
                    "status": row.status,
                },
                metadata_json={"source": "service"},
            )

        return created_rows

    def list_recommendations(
        self,
        org_id: uuid.UUID,
        system_id: uuid.UUID | None = None,
        status_value: str | None = None,
        priority: str | None = None,
    ) -> list[AIRiskRecommendation]:
        stmt = select(AIRiskRecommendation).where(AIRiskRecommendation.organization_id == org_id)
        if system_id is not None:
            stmt = stmt.where(AIRiskRecommendation.ai_system_id == system_id)
        if status_value is not None:
            if status_value not in ALLOWED_STATUS:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid status filter")
            stmt = stmt.where(AIRiskRecommendation.status == status_value)
        if priority is not None:
            if priority not in ALLOWED_PRIORITY:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid priority filter")
            stmt = stmt.where(AIRiskRecommendation.priority == priority)
        return self.db.execute(stmt.order_by(AIRiskRecommendation.created_at.desc())).scalars().all()

    def apply_recommendation(self, org_id: uuid.UUID, rec_id: uuid.UUID, user_id: uuid.UUID) -> AIRiskRecommendation:
        row = self._require_recommendation(org_id, rec_id)
        if row.status == "dismissed":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Dismissed recommendation cannot be applied")
        if row.status == "applied":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Recommendation already applied")

        now = self.utcnow()
        row.status = "applied"
        row.updated_at = now

        task = Task(
            organization_id=org_id,
            title=row.recommendation_text[:100],
            description=f"{row.recommendation_text}\n\n{CAVEAT}",
            status="open",
            priority=row.priority,
            task_type="risk_treatment",
            owner_user_id=user_id,
            created_by_user_id=user_id,
            linked_entity_type="general",
            linked_entity_id=row.id,
            source="system",
            reminder_status="none",
            metadata_json={
                "source_type": row.source_type,
                "recommendation_id": str(row.id),
            },
        )
        self.db.add(task)
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "recommendation.applied",
            actor_id=user_id,
            actor_type="user",
            ai_system_id=row.ai_system_id,
            event_data={"recommendation_id": str(row.id), "task_id": str(task.id)},
        )
        AuditService(self.db).write_audit_log(
            action="recommendation.applied",
            entity_type="ai_risk_recommendation",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status, "task_id": str(task.id)},
            metadata_json={"source": "api"},
        )
        return row

    def dismiss_recommendation(self, org_id: uuid.UUID, rec_id: uuid.UUID, user_id: uuid.UUID) -> AIRiskRecommendation:
        row = self._require_recommendation(org_id, rec_id)
        row.status = "dismissed"
        row.updated_at = self.utcnow()
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "recommendation.dismissed",
            actor_id=user_id,
            actor_type="user",
            ai_system_id=row.ai_system_id,
            event_data={"recommendation_id": str(row.id)},
        )
        AuditService(self.db).write_audit_log(
            action="recommendation.dismissed",
            entity_type="ai_risk_recommendation",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status},
            metadata_json={"source": "api"},
        )
        return row
