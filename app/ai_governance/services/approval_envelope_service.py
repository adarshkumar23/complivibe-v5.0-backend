import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_governance.services.ai_governance_event_service import AIGovernanceEventService
from app.models.ai_approval_envelope import AIApprovalEnvelope
from app.models.ai_envelope_approval import AIEnvelopeApproval
from app.models.ai_system import AISystem
from app.services.audit_service import AuditService


class ApprovalEnvelopeService:
    def __init__(self, db: Session) -> None:
        self.db = db

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

    def _require_envelope(self, org_id: uuid.UUID, envelope_id: uuid.UUID) -> AIApprovalEnvelope:
        row = self.db.execute(
            select(AIApprovalEnvelope).where(
                AIApprovalEnvelope.organization_id == org_id,
                AIApprovalEnvelope.id == envelope_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval envelope not found")
        self._expire_if_needed(row)
        self.db.flush()
        return row

    def _expire_if_needed(self, envelope: AIApprovalEnvelope) -> None:
        now = self.utcnow()
        expires_at = envelope.expires_at
        now_cmp = now if getattr(expires_at, "tzinfo", None) is not None else now.replace(tzinfo=None)
        if envelope.status == "pending" and expires_at < now_cmp:
            envelope.status = "expired"
            envelope.updated_at = now
            AIGovernanceEventService.log(
                self.db,
                envelope.organization_id,
                "approval_envelope.expired",
                actor_id=None,
                actor_type="system",
                ai_system_id=envelope.ai_system_id,
                event_data={"envelope_id": str(envelope.id)},
            )
            AuditService(self.db).write_audit_log(
                action="approval_envelope.expired",
                entity_type="ai_approval_envelope",
                entity_id=envelope.id,
                organization_id=envelope.organization_id,
                actor_user_id=None,
                after_json={"status": envelope.status},
                metadata_json={"source": "lazy_expiry"},
            )

    def create_envelope(
        self,
        org_id: uuid.UUID,
        system_id: uuid.UUID,
        transition_from: str,
        transition_to: str,
        required_approvers: list[uuid.UUID],
        conditions: list,
        created_by: uuid.UUID,
    ) -> AIApprovalEnvelope:
        system = self._require_system(org_id, system_id)

        if system.risk_tier in {"high", "prohibited"} and transition_to == "production" and len(required_approvers) < 2:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="High-risk systems require minimum 2 approvers for production deployment.",
            )

        now = self.utcnow()
        envelope = AIApprovalEnvelope(
            organization_id=org_id,
            ai_system_id=system_id,
            transition_from=transition_from,
            transition_to=transition_to,
            required_approvers=[str(item) for item in required_approvers],
            approvals_received={},
            conditions=conditions or [],
            status="pending",
            expires_at=now + timedelta(days=30),
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        self.db.add(envelope)
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "approval_envelope.created",
            actor_id=created_by,
            actor_type="user",
            ai_system_id=system_id,
            event_data={"envelope_id": str(envelope.id), "required_approvers": envelope.required_approvers},
        )
        AuditService(self.db).write_audit_log(
            action="approval_envelope.created",
            entity_type="ai_approval_envelope",
            entity_id=envelope.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={"status": envelope.status, "transition_to": envelope.transition_to},
            metadata_json={"source": "api"},
        )
        return envelope

    def get_envelope(self, org_id: uuid.UUID, envelope_id: uuid.UUID) -> AIApprovalEnvelope:
        return self._require_envelope(org_id, envelope_id)

    def list_envelopes(
        self,
        org_id: uuid.UUID,
        system_id: uuid.UUID | None = None,
        status_filter: str | None = None,
    ) -> list[AIApprovalEnvelope]:
        stmt = select(AIApprovalEnvelope).where(AIApprovalEnvelope.organization_id == org_id)
        if system_id is not None:
            stmt = stmt.where(AIApprovalEnvelope.ai_system_id == system_id)
        if status_filter is not None:
            if status_filter not in {"pending", "approved", "rejected", "expired"}:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid status filter")
            stmt = stmt.where(AIApprovalEnvelope.status == status_filter)
        rows = self.db.execute(stmt.order_by(AIApprovalEnvelope.created_at.desc())).scalars().all()
        for row in rows:
            self._expire_if_needed(row)
        self.db.flush()
        return rows

    def _ensure_actor_allowed(self, envelope: AIApprovalEnvelope, approver_id: uuid.UUID) -> None:
        approver_key = str(approver_id)
        required = set(str(item) for item in list(envelope.required_approvers or []))
        if approver_key not in required:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Approver is not in required_approvers")

        existing_vote = self.db.execute(
            select(AIEnvelopeApproval).where(
                AIEnvelopeApproval.envelope_id == envelope.id,
                AIEnvelopeApproval.approver_id == approver_id,
            )
        ).scalar_one_or_none()
        if existing_vote is not None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Approver has already voted")

    def _update_status_from_votes(self, envelope: AIApprovalEnvelope) -> None:
        required = [str(item) for item in list(envelope.required_approvers or [])]
        votes = dict(envelope.approvals_received or {})

        if any(votes.get(approver) == "rejected" for approver in required):
            envelope.status = "rejected"
            return

        if required and all(votes.get(approver) == "approved" for approver in required):
            envelope.status = "approved"
            return

        envelope.status = "pending"

    def approve_envelope(self, org_id: uuid.UUID, envelope_id: uuid.UUID, approver_id: uuid.UUID, notes: str | None = None) -> AIApprovalEnvelope:
        envelope = self._require_envelope(org_id, envelope_id)
        if envelope.status != "pending":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Envelope is not pending")

        self._ensure_actor_allowed(envelope, approver_id)
        now = self.utcnow()

        approval_row = AIEnvelopeApproval(
            envelope_id=envelope.id,
            approver_id=approver_id,
            decision="approved",
            notes=notes,
            decided_at=now,
        )
        self.db.add(approval_row)

        approvals_received = dict(envelope.approvals_received or {})
        approvals_received[str(approver_id)] = "approved"
        envelope.approvals_received = approvals_received
        envelope.updated_at = now
        self._update_status_from_votes(envelope)

        if envelope.status == "approved":
            system = self._require_system(org_id, envelope.ai_system_id)
            system.deployment_status = envelope.transition_to
            system.updated_at = now

            AIGovernanceEventService.log(
                self.db,
                org_id,
                "approval_envelope.approved",
                actor_id=approver_id,
                actor_type="user",
                ai_system_id=envelope.ai_system_id,
                event_data={"envelope_id": str(envelope.id)},
            )
            AIGovernanceEventService.log(
                self.db,
                org_id,
                "system.status_changed",
                actor_id=approver_id,
                actor_type="user",
                ai_system_id=envelope.ai_system_id,
                event_data={
                    "transition_from": envelope.transition_from,
                    "transition_to": envelope.transition_to,
                    "envelope_id": str(envelope.id),
                },
            )
            AuditService(self.db).write_audit_log(
                action="approval_envelope.approved",
                entity_type="ai_approval_envelope",
                entity_id=envelope.id,
                organization_id=org_id,
                actor_user_id=approver_id,
                after_json={"status": envelope.status, "transition_to": envelope.transition_to},
                metadata_json={"source": "api"},
            )

        self.db.flush()
        return envelope

    def reject_envelope(self, org_id: uuid.UUID, envelope_id: uuid.UUID, approver_id: uuid.UUID, notes: str) -> AIApprovalEnvelope:
        envelope = self._require_envelope(org_id, envelope_id)
        if envelope.status != "pending":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Envelope is not pending")

        self._ensure_actor_allowed(envelope, approver_id)
        now = self.utcnow()

        approval_row = AIEnvelopeApproval(
            envelope_id=envelope.id,
            approver_id=approver_id,
            decision="rejected",
            notes=notes,
            decided_at=now,
        )
        self.db.add(approval_row)

        approvals_received = dict(envelope.approvals_received or {})
        approvals_received[str(approver_id)] = "rejected"
        envelope.approvals_received = approvals_received
        envelope.status = "rejected"
        envelope.updated_at = now

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "approval_envelope.rejected",
            actor_id=approver_id,
            actor_type="user",
            ai_system_id=envelope.ai_system_id,
            event_data={"envelope_id": str(envelope.id)},
        )
        AuditService(self.db).write_audit_log(
            action="approval_envelope.rejected",
            entity_type="ai_approval_envelope",
            entity_id=envelope.id,
            organization_id=org_id,
            actor_user_id=approver_id,
            after_json={"status": envelope.status},
            metadata_json={"source": "api", "notes": notes},
        )
        self.db.flush()
        return envelope
