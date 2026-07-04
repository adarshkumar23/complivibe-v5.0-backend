import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_governance.services.ai_governance_event_service import AIGovernanceEventService
from app.ai_governance.services.ai_review_criteria import criteria_for_review_type
from app.models.ai_governance_review import AIGovernanceReview
from app.models.ai_review_criteria_response import AIReviewCriteriaResponse
from app.models.ai_system import AISystem
from app.services.audit_service import AuditService


class AIReviewService:
    ALLOWED_REVIEW_TYPES = {
        "initial_review",
        "pre_production_review",
        "periodic_review",
        "change_review",
        "retirement_review",
    }
    ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
        "pending": {"in_review"},
        "in_review": {"approved", "rejected", "conditional"},
        "approved": set(),
        "rejected": set(),
        "conditional": {"approved"},
    }
    ALLOWED_RESPONSES = {"yes", "no", "partial", "na"}

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _require_system(self, org_id: uuid.UUID, system_id: uuid.UUID) -> AISystem:
        row = self.db.execute(
            select(AISystem).where(
                AISystem.id == system_id,
                AISystem.organization_id == org_id,
                AISystem.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="AI system not found")
        return row

    def _require_review(self, org_id: uuid.UUID, review_id: uuid.UUID) -> AIGovernanceReview:
        row = self.db.execute(
            select(AIGovernanceReview).where(
                AIGovernanceReview.id == review_id,
                AIGovernanceReview.organization_id == org_id,
                AIGovernanceReview.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI governance review not found")
        return row

    def _transition(self, row: AIGovernanceReview, new_status: str) -> None:
        allowed = self.ALLOWED_STATUS_TRANSITIONS.get(row.status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status transition from {row.status} to {new_status}",
            )
        row.status = new_status

    def create_review(self, org_id: uuid.UUID, system_id: uuid.UUID, review_type: str, data, created_by: uuid.UUID) -> AIGovernanceReview:
        self._require_system(org_id, system_id)
        if review_type not in self.ALLOWED_REVIEW_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid review_type")
        if created_by == data.assigned_reviewer_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Review creator cannot be assigned reviewer")

        row = AIGovernanceReview(
            organization_id=org_id,
            ai_system_id=system_id,
            review_type=review_type,
            status="pending",
            assigned_reviewer_id=data.assigned_reviewer_id,
            due_date=data.due_date,
            created_by=created_by,
            conditions=[],
        )
        self.db.add(row)
        self.db.flush()

        criteria = criteria_for_review_type(review_type)
        for criterion_key, question in criteria.items():
            self.db.add(
                AIReviewCriteriaResponse(
                    organization_id=org_id,
                    review_id=row.id,
                    criterion_key=criterion_key,
                    question=question,
                    response=None,
                    notes=None,
                )
            )
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "review.initiated",
            actor_id=created_by,
            actor_type="user",
            ai_system_id=system_id,
            event_data={
                "review_id": str(row.id),
                "review_type": review_type,
                "assigned_reviewer_id": str(data.assigned_reviewer_id),
            },
        )
        AuditService(self.db).write_audit_log(
            action="ai_review.created",
            entity_type="ai_governance_review",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={
                "review_type": row.review_type,
                "status": row.status,
                "assigned_reviewer_id": str(row.assigned_reviewer_id),
            },
            metadata_json={"source": "api"},
        )
        return row

    def get_review(self, org_id: uuid.UUID, review_id: uuid.UUID) -> tuple[AIGovernanceReview, list[AIReviewCriteriaResponse]]:
        review = self._require_review(org_id, review_id)
        criteria_rows = self.db.execute(
            select(AIReviewCriteriaResponse).where(
                AIReviewCriteriaResponse.organization_id == org_id,
                AIReviewCriteriaResponse.review_id == review.id,
            )
        ).scalars().all()
        return review, criteria_rows

    def list_reviews(
        self,
        org_id: uuid.UUID,
        *,
        system_id: uuid.UUID | None = None,
        status_value: str | None = None,
        review_type: str | None = None,
    ) -> list[AIGovernanceReview]:
        stmt = select(AIGovernanceReview).where(
            AIGovernanceReview.organization_id == org_id,
            AIGovernanceReview.deleted_at.is_(None),
        )
        if system_id is not None:
            stmt = stmt.where(AIGovernanceReview.ai_system_id == system_id)
        if status_value is not None:
            stmt = stmt.where(AIGovernanceReview.status == status_value)
        if review_type is not None:
            stmt = stmt.where(AIGovernanceReview.review_type == review_type)
        return self.db.execute(stmt.order_by(AIGovernanceReview.created_at.desc())).scalars().all()

    def respond_to_criteria(self, org_id: uuid.UUID, review_id: uuid.UUID, responses: list[dict], user_id: uuid.UUID) -> AIGovernanceReview:
        review = self._require_review(org_id, review_id)
        if review.assigned_reviewer_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only assigned reviewer can respond")
        if review.status not in {"pending", "in_review"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Review is not open for criteria responses")

        criteria_map = {
            row.criterion_key: row
            for row in self.db.execute(
                select(AIReviewCriteriaResponse).where(
                    AIReviewCriteriaResponse.organization_id == org_id,
                    AIReviewCriteriaResponse.review_id == review.id,
                )
            ).scalars().all()
        }

        for item in responses:
            key = str(item["criterion_key"])
            row = criteria_map.get(key)
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Criterion not found: {key}")
            response_value = item.get("response")
            if response_value is not None and response_value not in self.ALLOWED_RESPONSES:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid criterion response value")
            row.response = response_value
            row.notes = item.get("notes")

        if review.status == "pending":
            self._transition(review, "in_review")

        self.db.flush()
        AIGovernanceEventService.log(
            self.db,
            org_id,
            "review.criteria_responded",
            actor_id=user_id,
            actor_type="user",
            ai_system_id=review.ai_system_id,
            event_data={"review_id": str(review.id), "responses_count": len(responses)},
        )
        AuditService(self.db).write_audit_log(
            action="ai_review.criteria_responded",
            entity_type="ai_governance_review",
            entity_id=review.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": review.status, "responses_count": len(responses)},
            metadata_json={"source": "api"},
        )
        return review

    def _require_all_criteria_answered(self, org_id: uuid.UUID, review_id: uuid.UUID) -> None:
        unanswered = self.db.execute(
            select(AIReviewCriteriaResponse).where(
                AIReviewCriteriaResponse.organization_id == org_id,
                AIReviewCriteriaResponse.review_id == review_id,
                AIReviewCriteriaResponse.response.is_(None),
            )
        ).scalars().all()
        if unanswered:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="All criteria must be responded before approval")

    def approve_review(self, org_id: uuid.UUID, review_id: uuid.UUID, user_id: uuid.UUID, decision_notes: str | None = None) -> AIGovernanceReview:
        review = self._require_review(org_id, review_id)
        if user_id == review.created_by:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Reviewer cannot approve their own review")
        self._require_all_criteria_answered(org_id, review.id)
        self._transition(review, "approved")
        review.completed_at = self.utcnow()
        review.decision_notes = decision_notes
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "review.completed",
            actor_id=user_id,
            actor_type="user",
            ai_system_id=review.ai_system_id,
            event_data={"review_id": str(review.id), "status": review.status},
        )
        AuditService(self.db).write_audit_log(
            action="ai_review.approved",
            entity_type="ai_governance_review",
            entity_id=review.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": review.status, "decision_notes": review.decision_notes},
            metadata_json={"source": "api"},
        )
        return review

    def reject_review(self, org_id: uuid.UUID, review_id: uuid.UUID, user_id: uuid.UUID, decision_notes: str) -> AIGovernanceReview:
        review = self._require_review(org_id, review_id)
        self._transition(review, "rejected")
        review.completed_at = self.utcnow()
        review.decision_notes = decision_notes
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "review.rejected",
            actor_id=user_id,
            actor_type="user",
            ai_system_id=review.ai_system_id,
            event_data={"review_id": str(review.id), "status": review.status},
        )
        AuditService(self.db).write_audit_log(
            action="ai_review.rejected",
            entity_type="ai_governance_review",
            entity_id=review.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": review.status, "decision_notes": review.decision_notes},
            metadata_json={"source": "api"},
        )
        return review

    def approve_with_conditions(
        self,
        org_id: uuid.UUID,
        review_id: uuid.UUID,
        user_id: uuid.UUID,
        conditions: list[str],
        decision_notes: str | None = None,
    ) -> AIGovernanceReview:
        review = self._require_review(org_id, review_id)
        self._transition(review, "conditional")
        review.conditions = list(conditions)
        review.decision_notes = decision_notes
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "review.conditional",
            actor_id=user_id,
            actor_type="user",
            ai_system_id=review.ai_system_id,
            event_data={"review_id": str(review.id), "conditions_count": len(conditions)},
        )
        AuditService(self.db).write_audit_log(
            action="ai_review.conditional",
            entity_type="ai_governance_review",
            entity_id=review.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": review.status, "conditions": review.conditions},
            metadata_json={"source": "api"},
        )
        return review

    def complete_conditional(self, org_id: uuid.UUID, review_id: uuid.UUID, user_id: uuid.UUID, notes: str | None = None) -> AIGovernanceReview:
        review = self._require_review(org_id, review_id)
        self._transition(review, "approved")
        review.completed_at = self.utcnow()
        if notes is not None:
            review.decision_notes = notes
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "review.completed",
            actor_id=user_id,
            actor_type="user",
            ai_system_id=review.ai_system_id,
            event_data={"review_id": str(review.id), "status": review.status},
        )
        AuditService(self.db).write_audit_log(
            action="ai_review.completed",
            entity_type="ai_governance_review",
            entity_id=review.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": review.status, "decision_notes": review.decision_notes},
            metadata_json={"source": "api"},
        )
        return review
