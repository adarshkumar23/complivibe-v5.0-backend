import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.control import Control
from app.models.finding_control_suggestion import CloudFindingControlMappingRule, FindingControlSuggestion
from app.services.audit_service import AuditService
from app.services.evidence_service import EvidenceService


class FindingControlMappingService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _find_matching_rule(self, org_id: uuid.UUID, finding_category: str) -> CloudFindingControlMappingRule | None:
        return self.db.execute(
            select(CloudFindingControlMappingRule).where(
                CloudFindingControlMappingRule.organization_id == org_id,
                CloudFindingControlMappingRule.finding_category == finding_category,
                CloudFindingControlMappingRule.is_active.is_(True),
            )
        ).scalar_one_or_none()

    def _resolve_target_control(self, org_id: uuid.UUID, rule: CloudFindingControlMappingRule) -> Control | None:
        if rule.target_control_id is not None:
            return self.db.get(Control, rule.target_control_id)
        if rule.target_control_common_tag:
            return self.db.execute(
                select(Control).where(
                    Control.organization_id == org_id,
                    Control.common_control_tag == rule.target_control_common_tag,
                )
            ).scalars().first()
        return None

    def suggest_for_finding(
        self,
        org_id: uuid.UUID,
        connector_event_id: uuid.UUID,
        evidence_item_id: uuid.UUID,
        finding_category: str,
        auto_apply_allowed: bool,
        actor_user_id: uuid.UUID | None,
    ) -> FindingControlSuggestion | None:
        rule = self._find_matching_rule(org_id, finding_category)
        if rule is None:
            return None
        control = self._resolve_target_control(org_id, rule)
        if control is None:
            return None

        now = self.utcnow()
        suggestion = FindingControlSuggestion(
            organization_id=org_id,
            connector_event_id=connector_event_id,
            evidence_item_id=evidence_item_id,
            suggested_control_id=control.id,
            confidence=rule.confidence,
            rationale=f"Matched rule for finding_category='{finding_category}' -> control '{control.title}'.",
            status="open",
            created_at=now,
            updated_at=now,
        )
        self.db.add(suggestion)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="finding_control_suggestion.created",
            entity_type="finding_control_suggestion",
            entity_id=suggestion.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={"suggested_control_id": str(control.id), "confidence": rule.confidence},
            metadata_json={"source": "system", "finding_category": finding_category},
        )

        if auto_apply_allowed and rule.confidence == "deterministic_exact":
            self.apply_suggestion(org_id, suggestion.id, actor_user_id=actor_user_id)
            self.db.refresh(suggestion)

        return suggestion

    def apply_suggestion(self, org_id: uuid.UUID, suggestion_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> FindingControlSuggestion:
        suggestion = self.db.execute(
            select(FindingControlSuggestion).where(
                FindingControlSuggestion.organization_id == org_id,
                FindingControlSuggestion.id == suggestion_id,
            )
        ).scalar_one_or_none()
        if suggestion is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding-control suggestion not found")
        if suggestion.status != "open":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Suggestion is not open")

        evidence_service = EvidenceService(self.db)
        evidence = evidence_service.require_evidence_in_org(org_id, suggestion.evidence_item_id)
        evidence_service._link_evidence_to_control(
            organization_id=org_id,
            evidence=evidence,
            target_control_id=suggestion.suggested_control_id,
            actor_user_id=actor_user_id,
            link_confidence=suggestion.confidence,
            link_rationale=suggestion.rationale,
            source="cloud_connector_finding_mapping",
            request_ip=None,
            request_user_agent=None,
        )

        now = self.utcnow()
        suggestion.status = "applied"
        suggestion.applied_by_user_id = actor_user_id
        suggestion.applied_at = now
        suggestion.updated_at = now
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="finding_control_suggestion.applied",
            entity_type="finding_control_suggestion",
            entity_id=suggestion.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={"suggested_control_id": str(suggestion.suggested_control_id)},
            metadata_json={"source": "api" if actor_user_id else "system"},
        )
        return suggestion

    def dismiss_suggestion(
        self, org_id: uuid.UUID, suggestion_id: uuid.UUID, reason: str, actor_user_id: uuid.UUID | None
    ) -> FindingControlSuggestion:
        suggestion = self.db.execute(
            select(FindingControlSuggestion).where(
                FindingControlSuggestion.organization_id == org_id,
                FindingControlSuggestion.id == suggestion_id,
            )
        ).scalar_one_or_none()
        if suggestion is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding-control suggestion not found")
        if suggestion.status != "open":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Suggestion is not open")

        now = self.utcnow()
        suggestion.status = "dismissed"
        suggestion.dismissed_by_user_id = actor_user_id
        suggestion.dismissed_at = now
        suggestion.dismissal_reason = reason
        suggestion.updated_at = now
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="finding_control_suggestion.dismissed",
            entity_type="finding_control_suggestion",
            entity_id=suggestion.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={"reason": reason},
            metadata_json={"source": "api"},
        )
        return suggestion
