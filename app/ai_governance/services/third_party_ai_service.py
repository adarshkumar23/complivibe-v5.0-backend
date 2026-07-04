import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_governance.services.ai_governance_event_service import AIGovernanceEventService
from app.models.ai_system import AISystem
from app.models.membership import Membership
from app.models.third_party_ai_assessment import ThirdPartyAIAssessment
from app.models.vendor import Vendor
from app.services.audit_service import AuditService
from app.core.validation import validate_choice

ALLOWED_DATA_EGRESS = {"none", "anonymized", "identified"}
ALLOWED_EXPLAINABILITY = {"full", "partial", "none", "not_required"}
ALLOWED_EU_ACT = {"compliant", "non_compliant", "unknown", "not_applicable"}
ALLOWED_RISK_LEVEL = {"low", "medium", "high", "critical"}
ALLOWED_STATUS = {"draft", "in_progress", "completed", "archived"}
NON_NULL_UPDATE_FIELDS = {
    "model_name",
    "data_egress_type",
    "model_card_provided",
    "bias_testing_documented",
    "contractual_ai_terms_reviewed",
    "status",
    "assessed_by",
}

# Severity order for ai_system.risk_tier. A third-party model assessment may
# escalate a linked system's tier but must never downgrade one set by a more
# authoritative source (e.g. EU AI Act classification of high/prohibited).
RISK_TIER_SEVERITY = {"unassessed": 0, "minimal": 1, "limited": 2, "high": 3, "prohibited": 4}


class ThirdPartyAIService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _require_vendor(self, org_id: uuid.UUID, vendor_id: uuid.UUID) -> Vendor:
        row = self.db.execute(
            select(Vendor).where(
                Vendor.organization_id == org_id,
                Vendor.id == vendor_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")
        return row

    def _require_ai_system(self, org_id: uuid.UUID, ai_system_id: uuid.UUID) -> AISystem:
        row = self.db.execute(
            select(AISystem).where(
                AISystem.organization_id == org_id,
                AISystem.id == ai_system_id,
                AISystem.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system not found")
        return row

    def _require_active_org_member(self, org_id: uuid.UUID, user_id: uuid.UUID) -> None:
        row = self.db.execute(
            select(Membership.id).where(
                Membership.organization_id == org_id,
                Membership.user_id == user_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="assessed_by must be an active member of the organization",
            )

    def _validate_update_nulls(self, payload: dict) -> None:
        for field in NON_NULL_UPDATE_FIELDS:
            if field in payload and payload[field] is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"{field} cannot be null",
                )

    @staticmethod
    def _audit_value(value):
        return str(value) if isinstance(value, uuid.UUID) else value

    def _validate_enums(self, payload: dict) -> None:
        if payload.get("data_egress_type") is not None and payload["data_egress_type"] not in ALLOWED_DATA_EGRESS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid data_egress_type")
        if payload.get("explainability_level") is not None and payload["explainability_level"] not in ALLOWED_EXPLAINABILITY:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid explainability_level")
        if payload.get("eu_act_compliance_status") is not None and payload["eu_act_compliance_status"] not in ALLOWED_EU_ACT:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid eu_act_compliance_status")
        if payload.get("overall_risk_level") is not None and payload["overall_risk_level"] not in ALLOWED_RISK_LEVEL:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid overall_risk_level")
        if payload.get("status") is not None and payload["status"] not in ALLOWED_STATUS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid status")

    def _require_assessment(self, org_id: uuid.UUID, assessment_id: uuid.UUID) -> ThirdPartyAIAssessment:
        row = self.db.execute(
            select(ThirdPartyAIAssessment).where(
                ThirdPartyAIAssessment.organization_id == org_id,
                ThirdPartyAIAssessment.id == assessment_id,
                ThirdPartyAIAssessment.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Third-party AI assessment not found")
        return row

    def create_assessment(self, org_id: uuid.UUID, vendor_id: uuid.UUID, data, created_by: uuid.UUID) -> ThirdPartyAIAssessment:
        self._require_vendor(org_id, vendor_id)
        payload = data.model_dump()
        self._validate_enums(payload)
        ai_system_id = payload.get("ai_system_id")
        if ai_system_id is not None:
            self._require_ai_system(org_id, ai_system_id)

        now = self.utcnow()
        row = ThirdPartyAIAssessment(
            organization_id=org_id,
            vendor_id=vendor_id,
            ai_system_id=ai_system_id,
            model_name=payload["model_name"],
            model_version=payload.get("model_version"),
            data_egress_type=payload["data_egress_type"],
            model_card_provided=payload["model_card_provided"],
            bias_testing_documented=payload["bias_testing_documented"],
            explainability_level=payload.get("explainability_level"),
            contractual_ai_terms_reviewed=payload["contractual_ai_terms_reviewed"],
            eu_act_compliance_status=payload.get("eu_act_compliance_status"),
            overall_risk_level=None,
            status=payload.get("status") or "draft",
            assessed_by=created_by,
            created_by=created_by,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
        self.db.add(row)
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "third_party_ai.created",
            actor_id=created_by,
            actor_type="user",
            ai_system_id=row.ai_system_id,
            event_data={"assessment_id": str(row.id), "vendor_id": str(vendor_id)},
        )
        AuditService(self.db).write_audit_log(
            action="third_party_ai.created",
            entity_type="third_party_ai_assessment",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={
                "vendor_id": str(row.vendor_id),
                "ai_system_id": str(row.ai_system_id) if row.ai_system_id else None,
                "status": row.status,
            },
            metadata_json={"source": "api"},
        )
        return row

    def get_assessment(self, org_id: uuid.UUID, assessment_id: uuid.UUID) -> ThirdPartyAIAssessment:
        return self._require_assessment(org_id, assessment_id)

    def list_assessments(
        self,
        org_id: uuid.UUID,
        vendor_id: uuid.UUID | None = None,
        status_filter: str | None = None,
        risk_level: str | None = None,
    ) -> list[ThirdPartyAIAssessment]:
        stmt = select(ThirdPartyAIAssessment).where(
            ThirdPartyAIAssessment.organization_id == org_id,
            ThirdPartyAIAssessment.deleted_at.is_(None),
        )
        if vendor_id is not None:
            stmt = stmt.where(ThirdPartyAIAssessment.vendor_id == vendor_id)
        if status_filter is not None:
            status_filter = validate_choice(status_filter, ALLOWED_STATUS, "status")
            stmt = stmt.where(ThirdPartyAIAssessment.status == status_filter)
        if risk_level is not None:
            risk_level = validate_choice(risk_level, ALLOWED_RISK_LEVEL, "risk_level")
            stmt = stmt.where(ThirdPartyAIAssessment.overall_risk_level == risk_level)
        return self.db.execute(stmt.order_by(ThirdPartyAIAssessment.created_at.desc())).scalars().all()

    def update_assessment(
        self,
        org_id: uuid.UUID,
        assessment_id: uuid.UUID,
        data,
        actor_user_id: uuid.UUID,
    ) -> ThirdPartyAIAssessment:
        row = self._require_assessment(org_id, assessment_id)
        if row.status in {"completed", "archived"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Assessment cannot be updated")

        payload = data.model_dump(exclude_unset=True)
        self._validate_update_nulls(payload)
        self._validate_enums(payload)
        if "ai_system_id" in payload and payload["ai_system_id"] is not None:
            self._require_ai_system(org_id, payload["ai_system_id"])
        if "assessed_by" in payload:
            self._require_active_org_member(org_id, payload["assessed_by"])

        before_json = {key: self._audit_value(getattr(row, key)) for key in payload}
        for key, value in payload.items():
            setattr(row, key, value)
        row.updated_at = self.utcnow()
        self.db.flush()
        after_json = {key: self._audit_value(getattr(row, key)) for key in payload}
        AuditService(self.db).write_audit_log(
            action="third_party_ai.updated",
            entity_type="third_party_ai_assessment",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            before_json=before_json,
            after_json=after_json,
            metadata_json={"source": "api"},
        )
        return row

    def _compute_score(self, row: ThirdPartyAIAssessment) -> int:
        score = 0
        if row.data_egress_type == "identified":
            score += 30
        elif row.data_egress_type == "anonymized":
            score += 10

        if not row.bias_testing_documented:
            score += 20
        if not row.model_card_provided:
            score += 15
        if not row.contractual_ai_terms_reviewed:
            score += 20
        if row.explainability_level == "none":
            score += 15
        if row.eu_act_compliance_status == "non_compliant":
            score += 25
        return max(0, min(score, 100))

    @staticmethod
    def _risk_level_for_score(score: int) -> str:
        if score <= 25:
            return "low"
        if score <= 50:
            return "medium"
        if score <= 75:
            return "high"
        return "critical"

    def complete_assessment(self, org_id: uuid.UUID, assessment_id: uuid.UUID, user_id: uuid.UUID) -> ThirdPartyAIAssessment:
        row = self._require_assessment(org_id, assessment_id)
        if row.status == "archived":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Archived assessment cannot be completed")

        score = self._compute_score(row)
        risk_level = self._risk_level_for_score(score)

        row.overall_risk_level = risk_level
        row.status = "completed"
        row.assessed_by = user_id
        row.updated_at = self.utcnow()

        if row.ai_system_id is not None:
            system = self._require_ai_system(org_id, row.ai_system_id)
            tier_map = {
                "critical": "high",
                "high": "high",
                "medium": "limited",
                "low": "minimal",
            }
            proposed_tier = tier_map[risk_level]
            current_tier = system.risk_tier or "unassessed"
            if RISK_TIER_SEVERITY.get(proposed_tier, 0) > RISK_TIER_SEVERITY.get(current_tier, 0):
                system.risk_tier = proposed_tier
                AuditService(self.db).write_audit_log(
                    action="ai_system.risk_tier_escalated",
                    entity_type="ai_system",
                    entity_id=system.id,
                    organization_id=org_id,
                    actor_user_id=user_id,
                    before_json={"risk_tier": current_tier},
                    after_json={"risk_tier": proposed_tier},
                    metadata_json={
                        "source": "third_party_ai_assessment",
                        "assessment_id": str(row.id),
                    },
                )

        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "third_party_ai.completed",
            actor_id=user_id,
            actor_type="user",
            ai_system_id=row.ai_system_id,
            event_data={
                "assessment_id": str(row.id),
                "vendor_id": str(row.vendor_id),
                "risk_score": score,
                "overall_risk_level": row.overall_risk_level,
            },
        )
        AuditService(self.db).write_audit_log(
            action="third_party_ai.completed",
            entity_type="third_party_ai_assessment",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={
                "status": row.status,
                "overall_risk_level": row.overall_risk_level,
                "risk_score": score,
            },
            metadata_json={"source": "api"},
        )
        return row

    def soft_delete_assessment(self, org_id: uuid.UUID, assessment_id: uuid.UUID, user_id: uuid.UUID) -> ThirdPartyAIAssessment:
        row = self._require_assessment(org_id, assessment_id)
        if row.status != "draft":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only draft assessments can be deleted")

        row.deleted_at = self.utcnow()
        row.updated_at = row.deleted_at
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "third_party_ai.deleted",
            actor_id=user_id,
            actor_type="user",
            ai_system_id=row.ai_system_id,
            event_data={"assessment_id": str(row.id), "vendor_id": str(row.vendor_id)},
        )
        AuditService(self.db).write_audit_log(
            action="third_party_ai.deleted",
            entity_type="third_party_ai_assessment",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"deleted_at": row.deleted_at.isoformat(), "status": row.status},
            metadata_json={"source": "api"},
        )
        return row
