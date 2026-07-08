import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_governance.services.ai_governance_event_service import AIGovernanceEventService
from app.models.ai_approval_envelope import AIApprovalEnvelope
from app.models.ai_envelope_approval import AIEnvelopeApproval
from app.models.ai_system import AISystem
from app.models.membership import Membership
from app.models.user import User
from app.services.audit_service import AuditService

APPROVAL_ENVELOPE_STALE_DAYS = 7


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

    def _active_org_user_ids(self, org_id: uuid.UUID, user_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        if not user_ids:
            return set()
        return set(
            self.db.execute(
                select(User.id)
                .join(Membership, Membership.user_id == User.id)
                .where(
                    User.id.in_(user_ids),
                    User.is_active.is_(True),
                    User.status == "active",
                    Membership.organization_id == org_id,
                    Membership.status == "active",
                )
            ).scalars().all()
        )

    def _normalize_required_approvers(self, org_id: uuid.UUID, required_approvers: list[uuid.UUID]) -> list[str]:
        unique_ids: list[uuid.UUID] = []
        seen: set[uuid.UUID] = set()
        for user_id in required_approvers:
            if user_id in seen:
                continue
            seen.add(user_id)
            unique_ids.append(user_id)
        if not unique_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="required_approvers must include at least one active organization user",
            )

        valid_user_ids = self._active_org_user_ids(org_id, unique_ids)
        missing = [str(user_id) for user_id in unique_ids if user_id not in valid_user_ids]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"required_approvers includes users that are not active in organization: {', '.join(missing)}",
            )
        return [str(user_id) for user_id in unique_ids]

    @staticmethod
    def _normalize_conditions(conditions: list) -> list:
        cleaned: list = []
        for condition in list(conditions or []):
            if isinstance(condition, str):
                normalized = condition.strip()
                if normalized:
                    cleaned.append(normalized)
            elif condition is not None:
                cleaned.append(condition)
        return cleaned

    @staticmethod
    def _normalize_optional_notes(notes: str | None) -> str | None:
        if notes is None:
            return None
        normalized = notes.strip()
        return normalized or None

    def _require_reject_notes(self, notes: str) -> str:
        normalized = notes.strip()
        if not normalized:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="notes must not be empty")
        return normalized

    def _is_stale_pending(self, *, updated_at: datetime, envelope_status: str) -> bool:
        if envelope_status != "pending":
            return False
        now = self.utcnow()
        reference = updated_at
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        return reference <= (now - timedelta(days=APPROVAL_ENVELOPE_STALE_DAYS))

    def _system_deployment_status_map(self, org_id: uuid.UUID, system_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not system_ids:
            return {}
        rows = self.db.execute(
            select(AISystem.id, AISystem.deployment_status).where(
                AISystem.organization_id == org_id,
                AISystem.id.in_(system_ids),
                AISystem.deleted_at.is_(None),
            )
        ).all()
        return {row[0]: row[1] for row in rows}

    def envelope_payload(self, envelope: AIApprovalEnvelope, system_deployment_status: str | None) -> dict:
        required_approvers = [str(item) for item in list(envelope.required_approvers or [])]
        approvals_received = dict(envelope.approvals_received or {})
        approved_approvers = [item for item in required_approvers if approvals_received.get(item) == "approved"]
        rejected_approvers = [item for item in required_approvers if approvals_received.get(item) == "rejected"]
        pending_approvers = [item for item in required_approvers if approvals_received.get(item) not in {"approved", "rejected"}]
        required_count = len(required_approvers)
        approvals_count = len(approved_approvers)
        approval_progress_pct = round((approvals_count / required_count) * 100.0, 2) if required_count > 0 else 0.0
        stale_pending = self._is_stale_pending(updated_at=envelope.updated_at, envelope_status=envelope.status)
        has_context_drift = bool(
            envelope.status == "pending"
            and system_deployment_status is not None
            and system_deployment_status != envelope.transition_from
        )

        context_flags: list[str] = []
        if envelope.status == "pending" and pending_approvers:
            context_flags.append("missing_required_votes")
        if stale_pending:
            context_flags.append("stale_pending")
        if has_context_drift:
            context_flags.append("deployment_status_drift")
        if system_deployment_status is None:
            context_flags.append("system_missing")
        if envelope.status == "approved":
            context_flags.append("envelope_approved")
        if rejected_approvers:
            context_flags.append("rejected_vote_recorded")

        return {
            "id": envelope.id,
            "organization_id": envelope.organization_id,
            "ai_system_id": envelope.ai_system_id,
            "transition_from": envelope.transition_from,
            "transition_to": envelope.transition_to,
            "required_approvers": required_approvers,
            "approvals_received": approvals_received,
            "conditions": list(envelope.conditions or []),
            "status": envelope.status,
            "expires_at": envelope.expires_at,
            "created_by": envelope.created_by,
            "created_at": envelope.created_at,
            "updated_at": envelope.updated_at,
            "required_approver_count": required_count,
            "approvals_count": approvals_count,
            "approval_progress_pct": approval_progress_pct,
            "pending_approver_ids": pending_approvers,
            "rejected_approver_ids": rejected_approvers,
            "system_deployment_status": system_deployment_status,
            "stale_pending": stale_pending,
            "has_context_drift": has_context_drift,
            "context_flags": context_flags,
        }

    def envelope_payloads(self, org_id: uuid.UUID, rows: list[AIApprovalEnvelope]) -> list[dict]:
        system_status_map = self._system_deployment_status_map(
            org_id,
            [row.ai_system_id for row in rows],
        )
        return [self.envelope_payload(row, system_status_map.get(row.ai_system_id)) for row in rows]

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
        if transition_from == transition_to:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="transition_from and transition_to must be different",
            )
        normalized_approvers = self._normalize_required_approvers(org_id, required_approvers)

        if system.risk_tier in {"high", "prohibited"} and transition_to == "production" and len(normalized_approvers) < 2:
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
            required_approvers=normalized_approvers,
            approvals_received={},
            conditions=self._normalize_conditions(conditions),
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
        notes_value = self._normalize_optional_notes(notes)

        approval_row = AIEnvelopeApproval(
            envelope_id=envelope.id,
            approver_id=approver_id,
            decision="approved",
            notes=notes_value,
            decided_at=now,
        )
        self.db.add(approval_row)

        approvals_received = dict(envelope.approvals_received or {})
        approvals_received[str(approver_id)] = "approved"
        envelope.approvals_received = approvals_received
        envelope.updated_at = now
        self._update_status_from_votes(envelope)

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "approval_envelope.vote_recorded",
            actor_id=approver_id,
            actor_type="user",
            ai_system_id=envelope.ai_system_id,
            event_data={
                "envelope_id": str(envelope.id),
                "decision": "approved",
                "status": envelope.status,
            },
        )
        AuditService(self.db).write_audit_log(
            action="approval_envelope.vote_recorded",
            entity_type="ai_approval_envelope",
            entity_id=envelope.id,
            organization_id=org_id,
            actor_user_id=approver_id,
            after_json={
                "status": envelope.status,
                "decision": "approved",
                "approvals_count": int(
                    sum(1 for value in dict(envelope.approvals_received or {}).values() if value == "approved")
                ),
            },
            metadata_json={"source": "api"},
        )

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
        normalized_notes = self._require_reject_notes(notes)

        approval_row = AIEnvelopeApproval(
            envelope_id=envelope.id,
            approver_id=approver_id,
            decision="rejected",
            notes=normalized_notes,
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
            "approval_envelope.vote_recorded",
            actor_id=approver_id,
            actor_type="user",
            ai_system_id=envelope.ai_system_id,
            event_data={
                "envelope_id": str(envelope.id),
                "decision": "rejected",
                "status": envelope.status,
            },
        )
        AuditService(self.db).write_audit_log(
            action="approval_envelope.vote_recorded",
            entity_type="ai_approval_envelope",
            entity_id=envelope.id,
            organization_id=org_id,
            actor_user_id=approver_id,
            after_json={
                "status": envelope.status,
                "decision": "rejected",
                "approvals_count": int(
                    sum(1 for value in dict(envelope.approvals_received or {}).values() if value == "approved")
                ),
            },
            metadata_json={"source": "api"},
        )

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
            metadata_json={"source": "api", "notes": normalized_notes},
        )
        self.db.flush()
        return envelope
