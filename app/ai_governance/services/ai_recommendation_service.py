import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai_governance.services.ai_governance_event_service import AIGovernanceEventService
from app.ai_governance.services.ai_recommendation_engine import CAVEAT, AIRecommendationEngine
from app.models.ai_risk_assessment import AIRiskAssessment
from app.models.ai_risk_recommendation import AIRiskRecommendation
from app.models.ai_system import AISystem
from app.models.task import Task
from app.services.audit_service import AuditService
from app.core.validation import validate_choice

ALLOWED_SOURCE_TYPES = {"risk_assessment", "monitoring_breach", "signal", "manual"}
ALLOWED_RECOMMENDATION_CATEGORY = {"technical_control", "process_control", "documentation", "audit", "decommission"}
ALLOWED_PRIORITY = {"critical", "high", "medium", "low"}
ALLOWED_STATUS = {"active", "applied", "dismissed"}
RECOMMENDATION_SOURCE_STALE_DAYS = 30
PRIORITY_ACTION_DAYS = {"critical": 7, "high": 14, "medium": 30, "low": 60}


class AIRecommendationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.engine = AIRecommendationEngine()

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

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

    def _assessment_map(self, source_ref_ids: list[uuid.UUID]) -> dict[uuid.UUID, AIRiskAssessment]:
        if not source_ref_ids:
            return {}
        rows = self.db.execute(select(AIRiskAssessment).where(AIRiskAssessment.id.in_(source_ref_ids))).scalars().all()
        return {row.id: row for row in rows}

    def _task_count_map(self, org_id: uuid.UUID, recommendation_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not recommendation_ids:
            return {}
        rows = self.db.execute(
            select(Task.linked_entity_id, func.count(Task.id))
            .where(
                Task.organization_id == org_id,
                Task.linked_entity_id.in_(recommendation_ids),
            )
            .group_by(Task.linked_entity_id)
        ).all()
        return {row[0]: int(row[1]) for row in rows if row[0] is not None}

    def recommendation_payload(
        self,
        row: AIRiskRecommendation,
        *,
        source_assessment: AIRiskAssessment | None,
        linked_task_count: int,
    ) -> dict:
        source_age_days: int | None = None
        stale_source = False
        source_updated_after_generation = False
        if source_assessment is not None and source_assessment.completed_at is not None:
            completed_at_utc = self._as_utc(source_assessment.completed_at)
            recommendation_updated_utc = self._as_utc(row.updated_at)
            assessment_updated_utc = self._as_utc(source_assessment.updated_at)
            now_utc = self._as_utc(self.utcnow())
            if completed_at_utc is not None and now_utc is not None:
                source_age_days = max(0, int((now_utc - completed_at_utc).total_seconds() // 86400))
            stale_source = source_age_days >= RECOMMENDATION_SOURCE_STALE_DAYS
            source_updated_after_generation = bool(
                assessment_updated_utc is not None
                and recommendation_updated_utc is not None
                and assessment_updated_utc > recommendation_updated_utc
            )

        action_due_in_days = int(PRIORITY_ACTION_DAYS.get(row.priority, PRIORITY_ACTION_DAYS["low"]))
        priority_weight = int({"critical": 4, "high": 3, "medium": 2, "low": 1}.get(row.priority, 1))

        context_flags: list[str] = []
        if row.status == "active":
            context_flags.append("action_pending")
        if row.status == "applied":
            context_flags.append("recommendation_applied")
        if row.status == "dismissed":
            context_flags.append("recommendation_dismissed")
        if linked_task_count > 0:
            context_flags.append("task_linked")
        if stale_source:
            context_flags.append("stale_source")
        if source_updated_after_generation:
            context_flags.append("source_updated_after_generation")

        return {
            "id": row.id,
            "organization_id": row.organization_id,
            "ai_system_id": row.ai_system_id,
            "source_type": row.source_type,
            "recommendation_text": row.recommendation_text,
            "recommendation_category": row.recommendation_category,
            "priority": row.priority,
            "status": row.status,
            "source_ref_id": row.source_ref_id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "priority_weight": priority_weight,
            "action_due_in_days": action_due_in_days,
            "linked_task_count": linked_task_count,
            "source_age_days": source_age_days,
            "stale_source": stale_source,
            "source_updated_after_generation": source_updated_after_generation,
            "context_flags": context_flags,
        }

    def recommendation_payloads(self, org_id: uuid.UUID, rows: list[AIRiskRecommendation]) -> list[dict]:
        source_ref_ids = [row.source_ref_id for row in rows if row.source_ref_id is not None]
        assessments = self._assessment_map(source_ref_ids)
        task_counts = self._task_count_map(org_id, [row.id for row in rows])
        return [
            self.recommendation_payload(
                row,
                source_assessment=assessments.get(row.source_ref_id) if row.source_ref_id is not None else None,
                linked_task_count=task_counts.get(row.id, 0),
            )
            for row in rows
        ]

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
            self._require_system(org_id, system_id)
            stmt = stmt.where(AIRiskRecommendation.ai_system_id == system_id)
        if status_value is not None:
            status_value = validate_choice(status_value, ALLOWED_STATUS, "status")
            stmt = stmt.where(AIRiskRecommendation.status == status_value)
        if priority is not None:
            priority = validate_choice(priority, ALLOWED_PRIORITY, "priority")
            stmt = stmt.where(AIRiskRecommendation.priority == priority)
        return self.db.execute(stmt.order_by(AIRiskRecommendation.created_at.desc())).scalars().all()

    def apply_recommendation(self, org_id: uuid.UUID, rec_id: uuid.UUID, user_id: uuid.UUID) -> AIRiskRecommendation:
        row = self._require_recommendation(org_id, rec_id)
        if row.status == "dismissed":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Dismissed recommendation cannot be applied")
        if row.status == "applied":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Recommendation already applied")
        existing_task = self.db.execute(
            select(Task.id).where(
                Task.organization_id == org_id,
                Task.linked_entity_id == row.id,
            )
        ).scalar_one_or_none()
        if existing_task is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Recommendation already has linked task",
            )

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
        if row.status == "dismissed":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Recommendation already dismissed")
        if row.status == "applied":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Applied recommendation cannot be dismissed")
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
