import uuid
from collections import Counter
from datetime import UTC, date, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ai_vendor_assessment import AIVendorAssessment
from app.models.email_outbox import EmailOutbox
from app.models.evidence_item import EvidenceItem
from app.models.membership import Membership
from app.models.vendor import Vendor
from app.models.vendor_assessment import VendorAssessment
from app.models.vendor_mitigation_action import VendorMitigationAction
from app.models.vendor_mitigation_case import VendorMitigationCase
from app.models.user import User
from app.services.audit_service import AuditService


class VendorMitigationService:
    CASE_TRANSITIONS: dict[str, set[str]] = {
        "open": {"in_progress", "cancelled"},
        "in_progress": {"pending_vendor_evidence", "under_review", "escalated", "cancelled"},
        "pending_vendor_evidence": {"under_review", "escalated"},
        "under_review": {"closed", "in_progress"},
        "closed": set(),
        "escalated": {"under_review", "closed"},
        "cancelled": set(),
    }

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def utcdate() -> date:
        return datetime.now(UTC).date()

    def _require_vendor(self, org_id: uuid.UUID, vendor_id: uuid.UUID) -> Vendor:
        row = self.db.execute(
            select(Vendor).where(
                Vendor.id == vendor_id,
                Vendor.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")
        return row

    def _require_case(self, org_id: uuid.UUID, case_id: uuid.UUID) -> VendorMitigationCase:
        row = self.db.execute(
            select(VendorMitigationCase).where(
                VendorMitigationCase.id == case_id,
                VendorMitigationCase.organization_id == org_id,
                VendorMitigationCase.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mitigation case not found")
        return row

    def _require_action(self, org_id: uuid.UUID, case_id: uuid.UUID, action_id: uuid.UUID) -> VendorMitigationAction:
        row = self.db.execute(
            select(VendorMitigationAction).where(
                VendorMitigationAction.id == action_id,
                VendorMitigationAction.case_id == case_id,
                VendorMitigationAction.organization_id == org_id,
                VendorMitigationAction.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mitigation action not found")
        return row

    def _require_assessment(self, org_id: uuid.UUID, assessment_id: uuid.UUID) -> VendorAssessment:
        row = self.db.execute(
            select(VendorAssessment).where(
                VendorAssessment.id == assessment_id,
                VendorAssessment.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor assessment not found")
        return row

    def _require_ai_assessment(self, org_id: uuid.UUID, ai_assessment_id: uuid.UUID) -> AIVendorAssessment:
        row = self.db.execute(
            select(AIVendorAssessment).where(
                AIVendorAssessment.id == ai_assessment_id,
                AIVendorAssessment.organization_id == org_id,
                AIVendorAssessment.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI vendor assessment not found")
        return row

    def _validate_case_assessment_refs(
        self,
        org_id: uuid.UUID,
        vendor_id: uuid.UUID,
        assessment_id: uuid.UUID | None,
        ai_assessment_id: uuid.UUID | None,
    ) -> None:
        if assessment_id is None and ai_assessment_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="assessment_id or ai_assessment_id is required",
            )
        if assessment_id is not None:
            assessment = self._require_assessment(org_id, assessment_id)
            if assessment.vendor_id != vendor_id:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="assessment vendor mismatch")
        if ai_assessment_id is not None:
            ai_assessment = self._require_ai_assessment(org_id, ai_assessment_id)
            if ai_assessment.vendor_id != vendor_id:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="ai assessment vendor mismatch")

    def _require_active_org_user(self, org_id: uuid.UUID, user_id: uuid.UUID | None, *, field_name: str) -> None:
        if user_id is None:
            return
        row = self.db.execute(
            select(User, Membership)
            .join(Membership, Membership.user_id == User.id)
            .where(User.id == user_id, Membership.organization_id == org_id)
        ).first()
        if row is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{field_name} must belong to this organization")
        user, membership = row
        if not user.is_active or user.status != "active" or membership.status != "active":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{field_name} must be an active organization member")

    def create_case(self, org_id: uuid.UUID, data, created_by: uuid.UUID) -> VendorMitigationCase:
        self._require_vendor(org_id, data.vendor_id)
        self._validate_case_assessment_refs(org_id, data.vendor_id, data.assessment_id, data.ai_assessment_id)
        self._require_active_org_user(org_id, data.assigned_owner_id, field_name="assigned_owner_id")

        row = VendorMitigationCase(
            organization_id=org_id,
            vendor_id=data.vendor_id,
            assessment_id=data.assessment_id,
            ai_assessment_id=data.ai_assessment_id,
            title=data.title,
            description=data.description,
            severity=data.severity,
            status="open",
            assigned_owner_id=data.assigned_owner_id,
            due_date=data.due_date,
            created_by=created_by,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="vendor_mitigation_case.created",
            entity_type="vendor_mitigation_case",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={"status": row.status, "severity": row.severity},
            metadata_json={"source": "api"},
        )
        return row

    def get_case(self, org_id: uuid.UUID, case_id: uuid.UUID) -> VendorMitigationCase:
        return self._require_case(org_id, case_id)

    def list_cases(
        self,
        org_id: uuid.UUID,
        *,
        vendor_id: uuid.UUID | None = None,
        status_value: str | None = None,
        severity: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[VendorMitigationCase]:
        stmt = select(VendorMitigationCase).where(
            VendorMitigationCase.organization_id == org_id,
            VendorMitigationCase.deleted_at.is_(None),
        )
        if vendor_id is not None:
            stmt = stmt.where(VendorMitigationCase.vendor_id == vendor_id)
        if status_value is not None:
            stmt = stmt.where(VendorMitigationCase.status == status_value)
        if severity is not None:
            stmt = stmt.where(VendorMitigationCase.severity == severity)

        return self.db.execute(stmt.order_by(VendorMitigationCase.created_at.desc()).offset(skip).limit(limit)).scalars().all()

    def transition_case(
        self,
        org_id: uuid.UUID,
        case_id: uuid.UUID,
        new_status: str,
        user_id: uuid.UUID,
        notes: str | None = None,
    ) -> VendorMitigationCase:
        row = self._require_case(org_id, case_id)
        allowed = self.CASE_TRANSITIONS.get(row.status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid case transition from {row.status} to {new_status}",
            )

        row.status = new_status
        if new_status == "closed":
            row.closed_at = self.utcnow()
            row.closed_by = user_id
            row.closure_notes = notes
        elif new_status == "escalated":
            row.escalated_at = self.utcnow()
            row.escalated_by = user_id
            row.escalation_reason = notes

        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="vendor_mitigation_case.transitioned",
            entity_type="vendor_mitigation_case",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def add_action(self, org_id: uuid.UUID, case_id: uuid.UUID, data) -> VendorMitigationAction:
        case = self._require_case(org_id, case_id)
        if case.status in {"closed", "cancelled", "escalated"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Cannot add actions to terminal/escalated cases")

        row = VendorMitigationAction(
            organization_id=org_id,
            case_id=case_id,
            title=data.title,
            description=data.description,
            action_type=data.action_type,
            assigned_to_vendor=data.assigned_to_vendor,
            due_date=data.due_date,
            status="open",
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="vendor_mitigation_action.added",
            entity_type="vendor_mitigation_action",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=None,
            after_json={"case_id": str(case_id), "status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def list_actions(self, org_id: uuid.UUID, case_id: uuid.UUID) -> list[VendorMitigationAction]:
        _ = self._require_case(org_id, case_id)
        return self.db.execute(
            select(VendorMitigationAction)
            .where(
                VendorMitigationAction.organization_id == org_id,
                VendorMitigationAction.case_id == case_id,
                VendorMitigationAction.deleted_at.is_(None),
            )
            .order_by(VendorMitigationAction.created_at.asc())
        ).scalars().all()

    def submit_action_evidence(
        self,
        org_id: uuid.UUID,
        case_id: uuid.UUID,
        action_id: uuid.UUID,
        evidence_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> VendorMitigationAction:
        case = self._require_case(org_id, case_id)
        row = self._require_action(org_id, case_id, action_id)

        evidence = self.db.execute(
            select(EvidenceItem).where(
                EvidenceItem.id == evidence_id,
                EvidenceItem.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if evidence is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="evidence_id not found in organization")

        row.evidence_id = evidence_id
        row.status = "evidence_submitted"
        row.evidence_submitted_at = self.utcnow()

        if row.assigned_to_vendor and case.status != "pending_vendor_evidence" and case.status not in {"closed", "cancelled"}:
            case.status = "pending_vendor_evidence"

        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="vendor_mitigation_action.evidence_submitted",
            entity_type="vendor_mitigation_action",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status, "evidence_id": str(evidence_id)},
            metadata_json={"source": "api"},
        )
        return row

    def accept_action(self, org_id: uuid.UUID, case_id: uuid.UUID, action_id: uuid.UUID, user_id: uuid.UUID) -> VendorMitigationAction:
        case = self._require_case(org_id, case_id)
        row = self._require_action(org_id, case_id, action_id)

        row.status = "accepted"
        row.accepted_at = self.utcnow()
        row.accepted_by = user_id
        self.db.flush()

        all_actions = self.db.execute(
            select(VendorMitigationAction).where(
                VendorMitigationAction.organization_id == org_id,
                VendorMitigationAction.case_id == case_id,
                VendorMitigationAction.deleted_at.is_(None),
            )
        ).scalars().all()
        if all_actions and all(item.status == "accepted" for item in all_actions):
            case.status = "under_review"

        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="vendor_mitigation_action.accepted",
            entity_type="vendor_mitigation_action",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status, "accepted_at": row.accepted_at.isoformat() if row.accepted_at else None},
            metadata_json={"source": "api"},
        )
        return row

    def reject_action(
        self,
        org_id: uuid.UUID,
        case_id: uuid.UUID,
        action_id: uuid.UUID,
        user_id: uuid.UUID,
        reason: str,
    ) -> VendorMitigationAction:
        row = self._require_action(org_id, case_id, action_id)
        row.status = "rejected"
        row.rejected_at = self.utcnow()
        row.rejected_by = user_id
        row.rejection_reason = reason
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="vendor_mitigation_action.rejected",
            entity_type="vendor_mitigation_action",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status, "reason": row.rejection_reason},
            metadata_json={"source": "api"},
        )
        return row

    def escalate_case(self, org_id: uuid.UUID, case_id: uuid.UUID, user_id: uuid.UUID, reason: str) -> VendorMitigationCase:
        row = self.transition_case(org_id, case_id, "escalated", user_id, notes=reason)

        owner = self.db.execute(select(User).where(User.id == row.assigned_owner_id)).scalar_one_or_none()
        if owner is not None and owner.email:
            self.db.add(
                EmailOutbox(
                    organization_id=org_id,
                    template_id=None,
                    event_type="vendor_mitigation.case_escalated",
                    recipient_email=owner.email,
                    recipient_user_id=owner.id,
                    subject=f"Mitigation case escalated: {row.title}",
                    body_text=f"Case {row.title} escalated. Reason: {reason}",
                    body_html=None,
                    status="pending",
                    priority="high",
                    scheduled_at=None,
                    queued_at=self.utcnow(),
                    attempt_count=0,
                    max_attempts=3,
                    metadata_json={"case_id": str(row.id), "source": "vendor_mitigation"},
                    created_by_user_id=user_id,
                )
            )

        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="vendor_mitigation_case.escalated",
            entity_type="vendor_mitigation_case",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status, "escalation_reason": row.escalation_reason},
            metadata_json={"source": "api"},
        )
        return row

    def get_mitigation_summary(self, org_id: uuid.UUID) -> dict:
        today = self.utcdate()

        cases = self.db.execute(
            select(VendorMitigationCase).where(
                VendorMitigationCase.organization_id == org_id,
                VendorMitigationCase.deleted_at.is_(None),
            )
        ).scalars().all()
        actions = self.db.execute(
            select(VendorMitigationAction).where(
                VendorMitigationAction.organization_id == org_id,
                VendorMitigationAction.deleted_at.is_(None),
            )
        ).scalars().all()

        by_status = Counter(row.status for row in cases)
        by_severity = Counter(row.severity for row in cases)
        actions_by_status = Counter(row.status for row in actions)

        overdue_cases = sum(1 for row in cases if row.due_date < today and row.status not in {"closed", "cancelled"})

        closed_durations = [
            (row.closed_at - row.created_at).total_seconds() / 86400
            for row in cases
            if row.status == "closed" and row.closed_at is not None
        ]
        avg_days_to_close = float(sum(closed_durations) / len(closed_durations)) if closed_durations else 0.0

        return {
            "total_cases": len(cases),
            "by_status": {k: int(v) for k, v in by_status.items()},
            "by_severity": {k: int(v) for k, v in by_severity.items()},
            "open_critical_count": int(sum(1 for row in cases if row.status == "open" and row.severity == "critical")),
            "overdue_cases": int(overdue_cases),
            "avg_days_to_close": avg_days_to_close,
            "pending_evidence_count": int(by_status.get("pending_vendor_evidence", 0)),
            "total_actions": len(actions),
            "actions_by_status": {k: int(v) for k, v in actions_by_status.items()},
        }

    def sweep_overdue_actions(self, org_id: uuid.UUID | None = None) -> dict[str, int]:
        today = self.utcdate()
        stmt = select(VendorMitigationAction).where(
            VendorMitigationAction.deleted_at.is_(None),
            VendorMitigationAction.due_date < today,
            VendorMitigationAction.status.in_(["open", "in_progress", "evidence_submitted"]),
        )
        if org_id is not None:
            stmt = stmt.where(VendorMitigationAction.organization_id == org_id)

        rows = self.db.execute(stmt).scalars().all()
        for row in rows:
            row.status = "overdue"

        self.db.flush()
        return {"marked_overdue": len(rows)}

    def soft_delete_case(self, org_id: uuid.UUID, case_id: uuid.UUID, user_id: uuid.UUID) -> VendorMitigationCase:
        row = self._require_case(org_id, case_id)
        if row.status != "open":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only open cases can be deleted")

        row.deleted_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="vendor_mitigation_case.deleted",
            entity_type="vendor_mitigation_case",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"deleted_at": row.deleted_at.isoformat() if row.deleted_at else None},
            metadata_json={"source": "api"},
        )
        return row


def run_daily_vendor_mitigation_overdue_action_sweep(db: Session) -> dict[str, int]:
    return VendorMitigationService(db).sweep_overdue_actions()
