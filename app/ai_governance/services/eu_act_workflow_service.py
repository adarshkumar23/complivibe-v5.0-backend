import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_governance.services.ai_governance_event_service import AIGovernanceEventService
from app.core.validation import validate_choice
from app.models.ai_system import AISystem
from app.models.eu_act_conformity_assessment import EUActConformityAssessment
from app.models.eu_act_fria import EUActFRIA
from app.models.eu_act_post_market_plan import EUActPostMarketPlan
from app.models.user import User
from app.services.audit_service import AuditService

CONFORMITY_ASSESSMENT_STATUSES = {"draft", "in_progress", "complete", "submitted"}
FRIA_STATUSES = {"draft", "in_progress", "complete"}
POST_MARKET_PLAN_STATUSES = {"draft", "active", "archived"}
EU_ACT_WORKFLOW_STALE_DAYS = 30

EU_ACT_CONFORMITY_CHECKLIST: list[dict[str, str]] = [
    {"key": "technical_documentation", "label": "Technical documentation prepared (Art. 11)"},
    {"key": "logging_record_keeping", "label": "Logging and record-keeping implemented (Art. 12)"},
    {"key": "transparency_requirements", "label": "Transparency requirements met (Art. 13)"},
    {"key": "human_oversight", "label": "Human oversight measures implemented (Art. 14)"},
    {"key": "accuracy_robustness", "label": "Accuracy, robustness and cybersecurity tested (Art. 15)"},
    {"key": "qms", "label": "Quality management system in place (Art. 17)"},
    {"key": "post_market_monitoring", "label": "Post-market monitoring plan established (Art. 61)"},
    {"key": "eu_database_registration", "label": "Registration in EU database completed (Art. 51)"},
]


class EUActWorkflowService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _is_stale_workflow(self, *, updated_at: datetime, status: str) -> bool:
        now = self.utcnow()
        reference = updated_at
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        return status in {"draft", "in_progress"} and reference <= (now - timedelta(days=EU_ACT_WORKFLOW_STALE_DAYS))

    @staticmethod
    def _has_text(value: str | None) -> bool:
        return bool(value is not None and str(value).strip())

    def conformity_payload(self, row: EUActConformityAssessment) -> dict:
        checklist = [dict(item) for item in list(row.checklist_items or [])]
        total_items = len(checklist)
        completed_items = int(sum(1 for item in checklist if bool(item.get("completed"))))
        completion_percent = round((completed_items / total_items) * 100.0, 2) if total_items > 0 else 0.0
        missing_keys = [str(item.get("key")) for item in checklist if not bool(item.get("completed")) and item.get("key")]
        stale_workflow = self._is_stale_workflow(updated_at=row.updated_at, status=row.status)
        context_flags: list[str] = []
        if row.status == "complete":
            context_flags.append("workflow_complete")
        if total_items > 0 and completed_items < total_items:
            context_flags.append("checklist_incomplete")
        if not bool(row.technical_documentation_complete):
            context_flags.append("technical_documentation_incomplete")
        if not bool(row.qms_compliant):
            context_flags.append("qms_not_confirmed")
        if stale_workflow:
            context_flags.append("stale_workflow")
        return {
            "id": row.id,
            "organization_id": row.organization_id,
            "ai_system_id": row.ai_system_id,
            "assessment_type": row.assessment_type,
            "status": row.status,
            "technical_documentation_complete": bool(row.technical_documentation_complete),
            "qms_compliant": bool(row.qms_compliant),
            "human_oversight_measures": row.human_oversight_measures,
            "accuracy_robustness_measures": row.accuracy_robustness_measures,
            "checklist_items": checklist,
            "checklist_total_items": total_items,
            "checklist_completed_items": completed_items,
            "checklist_completion_percent": completion_percent,
            "missing_checklist_item_keys": missing_keys,
            "stale_workflow": stale_workflow,
            "context_flags": context_flags,
            "created_by": row.created_by,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "deleted_at": row.deleted_at,
        }

    def fria_payload(self, row: EUActFRIA) -> dict:
        rights = list(row.rights_affected or [])
        rights_count = len(rights)
        has_risk_assessment = self._has_text(row.risk_to_rights_assessment)
        has_mitigation = self._has_text(row.mitigation_measures)
        completeness_parts = [
            bool(rights_count > 0),
            has_risk_assessment,
            has_mitigation,
            bool(row.consultation_conducted),
        ]
        completeness_percent = round((sum(1 for part in completeness_parts if part) / len(completeness_parts)) * 100.0, 2)
        stale_workflow = self._is_stale_workflow(updated_at=row.updated_at, status=row.status)
        context_flags: list[str] = []
        if row.status == "complete":
            context_flags.append("workflow_complete")
        if rights_count == 0:
            context_flags.append("rights_not_captured")
        if not has_risk_assessment:
            context_flags.append("risk_assessment_missing")
        if not has_mitigation:
            context_flags.append("mitigation_missing")
        if not bool(row.consultation_conducted):
            context_flags.append("consultation_not_conducted")
        if stale_workflow:
            context_flags.append("stale_workflow")
        return {
            "id": row.id,
            "organization_id": row.organization_id,
            "ai_system_id": row.ai_system_id,
            "rights_affected": rights,
            "risk_to_rights_assessment": row.risk_to_rights_assessment,
            "mitigation_measures": row.mitigation_measures,
            "consultation_conducted": bool(row.consultation_conducted),
            "status": row.status,
            "rights_affected_count": rights_count,
            "completeness_percent": completeness_percent,
            "stale_workflow": stale_workflow,
            "context_flags": context_flags,
            "created_by": row.created_by,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def post_market_plan_payload(self, row: EUActPostMarketPlan) -> dict:
        metrics = list(row.monitoring_metrics or [])
        metrics_count = len(metrics)
        has_reporting_frequency = self._has_text(row.reporting_frequency)
        has_incident_threshold = self._has_text(row.incident_reporting_threshold)
        has_responsible_person = bool(row.responsible_person_id is not None)
        completeness_parts = [bool(metrics_count > 0), has_reporting_frequency, has_incident_threshold, has_responsible_person]
        completeness_percent = round((sum(1 for part in completeness_parts if part) / len(completeness_parts)) * 100.0, 2)
        stale_workflow = self._is_stale_workflow(updated_at=row.updated_at, status=row.status)
        context_flags: list[str] = []
        if row.status == "active":
            context_flags.append("plan_active")
        if metrics_count == 0:
            context_flags.append("monitoring_metrics_missing")
        if not has_reporting_frequency:
            context_flags.append("reporting_frequency_missing")
        if not has_incident_threshold:
            context_flags.append("incident_threshold_missing")
        if stale_workflow:
            context_flags.append("stale_workflow")
        return {
            "id": row.id,
            "organization_id": row.organization_id,
            "ai_system_id": row.ai_system_id,
            "monitoring_metrics": metrics,
            "reporting_frequency": row.reporting_frequency,
            "incident_reporting_threshold": row.incident_reporting_threshold,
            "responsible_person_id": row.responsible_person_id,
            "status": row.status,
            "monitoring_metrics_count": metrics_count,
            "completeness_percent": completeness_percent,
            "stale_workflow": stale_workflow,
            "context_flags": context_flags,
            "created_by": row.created_by,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

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

    def _validate_user_exists(self, user_id: uuid.UUID, detail: str = "User not found") -> None:
        exists = self.db.execute(select(User.id).where(User.id == user_id)).scalar_one_or_none()
        if exists is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)

    def _conformity_for_system(self, org_id: uuid.UUID, system_id: uuid.UUID) -> EUActConformityAssessment | None:
        return self.db.execute(
            select(EUActConformityAssessment).where(
                EUActConformityAssessment.organization_id == org_id,
                EUActConformityAssessment.ai_system_id == system_id,
                EUActConformityAssessment.deleted_at.is_(None),
            )
        ).scalar_one_or_none()

    def create_conformity_assessment(self, org_id: uuid.UUID, system_id: uuid.UUID, data, created_by: uuid.UUID) -> EUActConformityAssessment:
        self._require_system(org_id, system_id)
        if self._conformity_for_system(org_id, system_id) is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Conformity assessment already exists for this AI system")

        if data.assessment_type not in {"self_assessment", "notified_body"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid assessment_type")

        now = self.utcnow()
        checklist = [{**item, "completed": False} for item in EU_ACT_CONFORMITY_CHECKLIST]
        row = EUActConformityAssessment(
            organization_id=org_id,
            ai_system_id=system_id,
            assessment_type=data.assessment_type,
            status="draft",
            technical_documentation_complete=data.technical_documentation_complete,
            qms_compliant=data.qms_compliant,
            human_oversight_measures=data.human_oversight_measures,
            accuracy_robustness_measures=data.accuracy_robustness_measures,
            checklist_items=checklist,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "eu_act.conformity_created",
            actor_id=created_by,
            actor_type="user",
            ai_system_id=system_id,
            event_data={"assessment_type": row.assessment_type},
        )
        AuditService(self.db).write_audit_log(
            action="eu_act.conformity_created",
            entity_type="eu_act_conformity_assessment",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={"status": row.status, "assessment_type": row.assessment_type},
            metadata_json={"source": "api"},
        )
        return row

    def get_conformity_assessment(self, org_id: uuid.UUID, system_id: uuid.UUID) -> EUActConformityAssessment:
        row = self._conformity_for_system(org_id, system_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conformity assessment not found")
        return row

    def update_conformity_assessment(self, org_id: uuid.UUID, assessment_id: uuid.UUID, data, actor_id: uuid.UUID) -> EUActConformityAssessment:
        row = self.db.execute(
            select(EUActConformityAssessment).where(
                EUActConformityAssessment.organization_id == org_id,
                EUActConformityAssessment.id == assessment_id,
                EUActConformityAssessment.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conformity assessment not found")

        payload = data.model_dump(exclude_unset=True)
        if payload.get("status") is not None:
            validate_choice(payload["status"], CONFORMITY_ASSESSMENT_STATUSES, "status")
        for key, value in payload.items():
            setattr(row, key, value)
        row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="eu_act.conformity_updated",
            entity_type="eu_act_conformity_assessment",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            after_json={"status": row.status},
            metadata_json={"source": "api", "op": "update"},
        )
        return row

    def complete_checklist_item(self, org_id: uuid.UUID, assessment_id: uuid.UUID, item_key: str, user_id: uuid.UUID) -> EUActConformityAssessment:
        row = self.db.execute(
            select(EUActConformityAssessment).where(
                EUActConformityAssessment.organization_id == org_id,
                EUActConformityAssessment.id == assessment_id,
                EUActConformityAssessment.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conformity assessment not found")
        if row.status in {"complete", "submitted"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Checklist items cannot be updated after completion")

        checklist = [dict(item) for item in list(row.checklist_items or [])]
        updated = False
        for item in checklist:
            if str(item.get("key")) == item_key:
                item["completed"] = True
                updated = True
                break
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checklist item not found")

        row.checklist_items = checklist
        row.status = "in_progress"
        row.updated_at = self.utcnow()
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "eu_act.conformity_item_completed",
            actor_id=user_id,
            actor_type="user",
            ai_system_id=row.ai_system_id,
            event_data={"assessment_id": str(row.id), "item_key": item_key},
        )
        AuditService(self.db).write_audit_log(
            action="eu_act.conformity_item_completed",
            entity_type="eu_act_conformity_assessment",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status, "item_key": item_key},
            metadata_json={"source": "api"},
        )
        return row

    def mark_complete(self, org_id: uuid.UUID, assessment_id: uuid.UUID, user_id: uuid.UUID) -> EUActConformityAssessment:
        row = self.db.execute(
            select(EUActConformityAssessment).where(
                EUActConformityAssessment.organization_id == org_id,
                EUActConformityAssessment.id == assessment_id,
                EUActConformityAssessment.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conformity assessment not found")

        checklist = list(row.checklist_items or [])
        if any(not bool(item.get("completed")) for item in checklist):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="All checklist items must be completed before marking complete",
            )

        row.status = "complete"
        row.updated_at = self.utcnow()
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "eu_act.conformity_completed",
            actor_id=user_id,
            actor_type="user",
            ai_system_id=row.ai_system_id,
            event_data={"assessment_id": str(row.id)},
        )
        AuditService(self.db).write_audit_log(
            action="eu_act.conformity_completed",
            entity_type="eu_act_conformity_assessment",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def _fria_for_system(self, org_id: uuid.UUID, system_id: uuid.UUID) -> EUActFRIA | None:
        return self.db.execute(
            select(EUActFRIA).where(
                EUActFRIA.organization_id == org_id,
                EUActFRIA.ai_system_id == system_id,
            )
        ).scalar_one_or_none()

    def create_fria(self, org_id: uuid.UUID, system_id: uuid.UUID, data, created_by: uuid.UUID) -> EUActFRIA:
        self._require_system(org_id, system_id)
        if self._fria_for_system(org_id, system_id) is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="FRIA already exists for this AI system")

        now = self.utcnow()
        row = EUActFRIA(
            organization_id=org_id,
            ai_system_id=system_id,
            rights_affected=data.rights_affected,
            risk_to_rights_assessment=data.risk_to_rights_assessment,
            mitigation_measures=data.mitigation_measures,
            consultation_conducted=data.consultation_conducted,
            status="draft",
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "eu_act.fria_created",
            actor_id=created_by,
            actor_type="user",
            ai_system_id=system_id,
            event_data={"fria_id": str(row.id)},
        )
        AuditService(self.db).write_audit_log(
            action="eu_act.fria_created",
            entity_type="eu_act_fria",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={"status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def get_fria(self, org_id: uuid.UUID, system_id: uuid.UUID) -> EUActFRIA:
        row = self._fria_for_system(org_id, system_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FRIA not found")
        return row

    def update_fria(self, org_id: uuid.UUID, fria_id: uuid.UUID, data, actor_id: uuid.UUID) -> EUActFRIA:
        row = self.db.execute(
            select(EUActFRIA).where(
                EUActFRIA.organization_id == org_id,
                EUActFRIA.id == fria_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FRIA not found")

        payload = data.model_dump(exclude_unset=True)
        if payload.get("status") is not None:
            validate_choice(payload["status"], FRIA_STATUSES, "status")
        for key, value in payload.items():
            setattr(row, key, value)
        row.status = "in_progress"
        row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="eu_act.fria_updated",
            entity_type="eu_act_fria",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            after_json={"status": row.status},
            metadata_json={"source": "api", "op": "update"},
        )
        return row

    def complete_fria(self, org_id: uuid.UUID, fria_id: uuid.UUID, user_id: uuid.UUID) -> EUActFRIA:
        row = self.db.execute(
            select(EUActFRIA).where(
                EUActFRIA.organization_id == org_id,
                EUActFRIA.id == fria_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FRIA not found")
        if not list(row.rights_affected or []):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="At least one right must be captured")
        if not self._has_text(row.risk_to_rights_assessment):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Risk-to-rights assessment is required")
        row.status = "complete"
        row.updated_at = self.utcnow()
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "eu_act.fria_completed",
            actor_id=user_id,
            actor_type="user",
            ai_system_id=row.ai_system_id,
            event_data={"fria_id": str(row.id)},
        )
        AuditService(self.db).write_audit_log(
            action="eu_act.fria_completed",
            entity_type="eu_act_fria",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def _plan_for_system(self, org_id: uuid.UUID, system_id: uuid.UUID) -> EUActPostMarketPlan | None:
        return self.db.execute(
            select(EUActPostMarketPlan).where(
                EUActPostMarketPlan.organization_id == org_id,
                EUActPostMarketPlan.ai_system_id == system_id,
            )
        ).scalar_one_or_none()

    def create_post_market_plan(self, org_id: uuid.UUID, system_id: uuid.UUID, data, created_by: uuid.UUID) -> EUActPostMarketPlan:
        self._require_system(org_id, system_id)
        if self._plan_for_system(org_id, system_id) is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Post-market plan already exists for this AI system")

        self._validate_user_exists(data.responsible_person_id, "Responsible person not found")

        now = self.utcnow()
        row = EUActPostMarketPlan(
            organization_id=org_id,
            ai_system_id=system_id,
            monitoring_metrics=data.monitoring_metrics,
            reporting_frequency=data.reporting_frequency,
            incident_reporting_threshold=data.incident_reporting_threshold,
            responsible_person_id=data.responsible_person_id,
            status="draft",
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "eu_act.post_market_created",
            actor_id=created_by,
            actor_type="user",
            ai_system_id=system_id,
            event_data={"plan_id": str(row.id)},
        )
        AuditService(self.db).write_audit_log(
            action="eu_act.post_market_updated",
            entity_type="eu_act_post_market_plan",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={"status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def get_post_market_plan(self, org_id: uuid.UUID, system_id: uuid.UUID) -> EUActPostMarketPlan:
        row = self._plan_for_system(org_id, system_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post-market plan not found")
        if row.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived post-market plan cannot be activated")
        if not list(row.monitoring_metrics or []):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Monitoring metrics are required")
        if not self._has_text(row.reporting_frequency):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Reporting frequency is required")
        self._validate_user_exists(row.responsible_person_id, "Responsible person not found")
        return row

    def update_post_market_plan(self, org_id: uuid.UUID, plan_id: uuid.UUID, data, actor_id: uuid.UUID) -> EUActPostMarketPlan:
        row = self.db.execute(
            select(EUActPostMarketPlan).where(
                EUActPostMarketPlan.organization_id == org_id,
                EUActPostMarketPlan.id == plan_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post-market plan not found")

        payload = data.model_dump(exclude_unset=True)
        if payload.get("responsible_person_id") is not None:
            self._validate_user_exists(payload["responsible_person_id"], "Responsible person not found")
        if payload.get("status") is not None:
            validate_choice(payload["status"], POST_MARKET_PLAN_STATUSES, "status")

        for key, value in payload.items():
            setattr(row, key, value)

        row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="eu_act.post_market_created",
            entity_type="eu_act_post_market_plan",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            after_json={"status": row.status},
            metadata_json={"source": "api", "op": "update"},
        )
        return row

    def activate_plan(self, org_id: uuid.UUID, plan_id: uuid.UUID, user_id: uuid.UUID) -> EUActPostMarketPlan:
        row = self.db.execute(
            select(EUActPostMarketPlan).where(
                EUActPostMarketPlan.organization_id == org_id,
                EUActPostMarketPlan.id == plan_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post-market plan not found")

        row.status = "active"
        row.updated_at = self.utcnow()
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "eu_act.post_market_activated",
            actor_id=user_id,
            actor_type="user",
            ai_system_id=row.ai_system_id,
            event_data={"plan_id": str(row.id)},
        )
        AuditService(self.db).write_audit_log(
            action="eu_act.post_market_activated",
            entity_type="eu_act_post_market_plan",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status},
            metadata_json={"source": "api"},
        )
        return row
