import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai_governance.schemas.ai_systems import AISystemCreate
from app.ai_governance.services.ai_governance_event_service import AIGovernanceEventService
from app.ai_governance.services.ai_system_service import AISystemService
from app.ai_governance.services.nlp.shadow_ai_scanner import KNOWN_AI_TOOLS, scan_text_for_shadow_ai
from app.models.ai_system import AISystem
from app.models.shadow_ai_detection import ShadowAIDetection
from app.services.audit_service import AuditService


class ShadowAIService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.ai_system_service = AISystemService(db)

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _find_active_detection(self, org_id: uuid.UUID, detected_name: str) -> ShadowAIDetection | None:
        normalized = detected_name.strip().lower()
        return self.db.execute(
            select(ShadowAIDetection).where(
                ShadowAIDetection.organization_id == org_id,
                func.lower(ShadowAIDetection.detected_name) == normalized,
                ShadowAIDetection.status.in_(["new", "under_review"]),
            )
        ).scalar_one_or_none()

    def report_detection(
        self,
        org_id: uuid.UUID,
        detected_name: str,
        detection_method: str,
        confidence: str,
        reported_by: uuid.UUID | None,
        notes: str | None = None,
    ) -> ShadowAIDetection:
        existing = self._find_active_detection(org_id, detected_name)
        if existing is not None:
            return existing

        row = ShadowAIDetection(
            organization_id=org_id,
            detected_name=detected_name.strip(),
            detection_method=detection_method,
            confidence=confidence,
            status="new",
            notes=notes,
            reported_by=reported_by,
        )
        self.db.add(row)
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "shadow_ai.detected",
            actor_id=reported_by,
            actor_type="user" if reported_by else "system",
            event_data={"detected_name": row.detected_name, "detection_method": detection_method},
        )

        if reported_by is not None:
            AuditService(self.db).write_audit_log(
                action="shadow_ai.reported",
                entity_type="shadow_ai_detection",
                entity_id=row.id,
                organization_id=org_id,
                actor_user_id=reported_by,
                after_json={
                    "detected_name": row.detected_name,
                    "detection_method": row.detection_method,
                    "confidence": row.confidence,
                    "status": row.status,
                },
                metadata_json={"source": "api"},
            )
        return row

    def list_detections(self, org_id: uuid.UUID, status_value: str | None = None) -> list[ShadowAIDetection]:
        stmt = select(ShadowAIDetection).where(ShadowAIDetection.organization_id == org_id)
        if status_value is not None:
            stmt = stmt.where(ShadowAIDetection.status == status_value)
        return self.db.execute(stmt.order_by(ShadowAIDetection.detected_at.desc())).scalars().all()

    def get_detection(self, org_id: uuid.UUID, detection_id: uuid.UUID) -> ShadowAIDetection:
        row = self.db.execute(
            select(ShadowAIDetection).where(
                ShadowAIDetection.organization_id == org_id,
                ShadowAIDetection.id == detection_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shadow AI detection not found")
        return row

    def review_detection(self, org_id: uuid.UUID, detection_id: uuid.UUID, reviewer_id: uuid.UUID) -> ShadowAIDetection:
        row = self.get_detection(org_id, detection_id)
        row.status = "under_review"
        row.reviewed_by = reviewer_id
        row.reviewed_at = self.utcnow()
        self.db.flush()
        return row

    def register_as_system(self, org_id: uuid.UUID, detection_id: uuid.UUID, system_data, user_id: uuid.UUID) -> AISystem:
        detection = self.get_detection(org_id, detection_id)
        if detection.status == "dismissed":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Dismissed detection cannot be registered")

        payload_dict = system_data.model_dump()
        if not payload_dict.get("name"):
            payload_dict["name"] = detection.detected_name

        payload = AISystemCreate(**payload_dict)
        system = self.ai_system_service.create_system(org_id, payload, user_id)

        detection.status = "registered"
        detection.reviewed_by = user_id
        detection.reviewed_at = self.utcnow()
        detection.registered_system_id = system.id
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "shadow_ai.registered",
            actor_id=user_id,
            actor_type="user",
            ai_system_id=system.id,
            event_data={"detection_id": str(detection.id), "detected_name": detection.detected_name},
        )
        AuditService(self.db).write_audit_log(
            action="shadow_ai.registered",
            entity_type="shadow_ai_detection",
            entity_id=detection.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": detection.status, "registered_system_id": str(system.id)},
            metadata_json={"source": "api"},
        )
        return system

    def dismiss_detection(
        self,
        org_id: uuid.UUID,
        detection_id: uuid.UUID,
        user_id: uuid.UUID,
        notes: str | None = None,
    ) -> ShadowAIDetection:
        row = self.get_detection(org_id, detection_id)
        row.status = "dismissed"
        row.reviewed_by = user_id
        row.reviewed_at = self.utcnow()
        if notes is not None:
            row.notes = notes
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "shadow_ai.dismissed",
            actor_id=user_id,
            actor_type="user",
            event_data={"detection_id": str(row.id), "detected_name": row.detected_name},
        )
        AuditService(self.db).write_audit_log(
            action="shadow_ai.dismissed",
            entity_type="shadow_ai_detection",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status, "notes": row.notes},
            metadata_json={"source": "api"},
        )
        return row

    def scan_and_create(self, org_id: uuid.UUID, text: str, reported_by: uuid.UUID | None) -> list[ShadowAIDetection]:
        hits = scan_text_for_shadow_ai(text)
        if not hits:
            return []

        existing_system_names = {
            str(name).strip().lower()
            for name in self.db.execute(
                select(AISystem.name).where(
                    AISystem.organization_id == org_id,
                    AISystem.deleted_at.is_(None),
                )
            ).scalars()
            if name
        }

        created: list[ShadowAIDetection] = []
        for hit in hits:
            detected_name = str(hit["detected_name"]).strip()
            if detected_name.lower() in existing_system_names:
                continue
            existing = self._find_active_detection(org_id, detected_name)
            if existing is not None:
                continue
            created.append(
                self.report_detection(
                    org_id,
                    detected_name=detected_name,
                    detection_method=str(hit.get("detection_method") or "questionnaire"),
                    confidence=str(hit.get("confidence") or "medium"),
                    reported_by=reported_by,
                )
            )
        return created
