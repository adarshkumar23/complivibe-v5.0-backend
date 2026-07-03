import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.framework import Framework
from app.models.framework_pack_coverage_report import FrameworkPackCoverageReport
from app.models.framework_pack_promotion_request import FrameworkPackPromotionRequest
from app.models.framework_pack_review_assignment import FrameworkPackReviewAssignment
from app.models.framework_pack_review_run import FrameworkPackReviewRun
from app.models.framework_pack_review_signoff import FrameworkPackReviewSignoff
from app.models.framework_review_escalation_event import FrameworkReviewEscalationEvent
from app.models.framework_review_sla_policy import FrameworkReviewSLAPolicy
from app.models.framework_version import FrameworkVersion
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from app.repositories.framework_pack_review_repository import FrameworkPackReviewRepository
from app.services.email_service import EmailService
from app.services.export_service import INTEGRITY_ALGORITHM, SIGNING_KEY_ID
from app.services.framework_content_pack_service import FrameworkContentPackService
from app.services.framework_content_service import FRAMEWORK_COVERAGE_LEVELS
from app.services.seed_service import SeedService
from app.core.validation import validate_choice

REVIEW_CAVEAT = (
    "Framework pack review and promotion are internal CompliVibe content-governance signals. "
    "They do not constitute legal advice, regulatory approval, or external audit certification."
)

REVIEW_TYPES = {"internal_review", "expert_review", "final_verification"}
REVIEW_STATUSES = {"running", "completed", "failed", "cancelled", "archived"}
REVIEW_OUTCOMES = {"pass", "fail", "needs_changes", "not_ready"}
SIGNOFF_DECISIONS = {"approved", "rejected"}
PROMOTION_STATUSES = {"pending", "approved", "rejected", "executed", "cancelled"}
ASSIGNMENT_STATUSES = {"assigned", "accepted", "completed", "cancelled", "overdue"}
SLA_POLICY_STATUSES = {"active", "inactive", "archived"}
ESCALATION_TYPES = {"reminder_due", "review_overdue", "signoff_missing", "promotion_pending_too_long"}
ESCALATION_STATUSES = {"open", "resolved", "dismissed"}

_COVERAGE_ORDER = ["metadata_only", "starter", "partial", "reviewed", "full_verified"]


class FrameworkPackReviewService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = FrameworkPackReviewRepository(db)
        self.pack_service = FrameworkContentPackService(db)

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _ensure_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _canonical_json(payload: dict[str, Any]) -> str:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    @staticmethod
    def _json_safe(payload: Any) -> Any:
        return json.loads(json.dumps(payload, default=str))

    def _checksum(self, payload: dict[str, Any]) -> str:
        canonical = self._canonical_json(payload).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def _signature(self, checksum_sha256: str) -> str:
        secret = get_settings().SECRET_KEY.encode("utf-8")
        return hmac.new(secret, checksum_sha256.encode("utf-8"), hashlib.sha256).hexdigest()

    @staticmethod
    def _require_coverage_level(value: str) -> None:
        value = validate_choice(value, FRAMEWORK_COVERAGE_LEVELS, "coverage_level", status_code=status.HTTP_400_BAD_REQUEST)
    @staticmethod
    def _require_review_type(value: str) -> None:
        value = validate_choice(value, REVIEW_TYPES, "review_type", status_code=status.HTTP_400_BAD_REQUEST)
    @staticmethod
    def _require_outcome(value: str) -> None:
        value = validate_choice(value, REVIEW_OUTCOMES, "outcome", status_code=status.HTTP_400_BAD_REQUEST)
    @staticmethod
    def _next_level(level: str) -> str | None:
        if level not in _COVERAGE_ORDER:
            return None
        idx = _COVERAGE_ORDER.index(level)
        if idx >= len(_COVERAGE_ORDER) - 1:
            return None
        return _COVERAGE_ORDER[idx + 1]

    @staticmethod
    def _validate_promotion_path(*, from_level: str, to_level: str) -> None:
        if from_level not in _COVERAGE_ORDER or to_level not in _COVERAGE_ORDER:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid coverage level")
        from_idx = _COVERAGE_ORDER.index(from_level)
        to_idx = _COVERAGE_ORDER.index(to_level)
        if to_idx <= from_idx:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Promotion must move to a higher coverage level")
        if to_idx - from_idx > 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot skip coverage levels during promotion")

    def require_framework(self, framework_id: uuid.UUID) -> Framework:
        framework = self.db.execute(select(Framework).where(Framework.id == framework_id)).scalar_one_or_none()
        if framework is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework not found")
        return framework

    def _active_version(self, framework_id: uuid.UUID) -> FrameworkVersion | None:
        return self.db.execute(
            select(FrameworkVersion)
            .where(FrameworkVersion.framework_id == framework_id, FrameworkVersion.status == "active")
            .order_by(FrameworkVersion.created_at.desc())
        ).scalars().first()

    def require_review(
        self,
        *,
        organization_id: uuid.UUID,
        framework_id: uuid.UUID,
        review_id: uuid.UUID,
    ) -> FrameworkPackReviewRun:
        row = self.repo.get_review(review_id)
        if row is None or row.organization_id != organization_id or row.framework_id != framework_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework pack review not found")
        return row

    def require_promotion(
        self,
        *,
        organization_id: uuid.UUID,
        framework_id: uuid.UUID,
        promotion_id: uuid.UUID,
    ) -> FrameworkPackPromotionRequest:
        row = self.repo.get_promotion(promotion_id)
        if row is None or row.organization_id != organization_id or row.framework_id != framework_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework pack promotion not found")
        return row

    def require_assignment(
        self,
        *,
        organization_id: uuid.UUID,
        assignment_id: uuid.UUID,
    ) -> FrameworkPackReviewAssignment:
        row = self.repo.get_assignment(assignment_id)
        if row is None or row.organization_id != organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework review assignment not found")
        return row

    def require_sla_policy(self, *, organization_id: uuid.UUID, policy_id: uuid.UUID) -> FrameworkReviewSLAPolicy:
        row = self.repo.get_sla_policy(policy_id)
        if row is None or row.organization_id != organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework review SLA policy not found")
        return row

    def require_escalation_event(self, *, organization_id: uuid.UUID, event_id: uuid.UUID) -> FrameworkReviewEscalationEvent:
        row = self.repo.get_escalation_event(event_id)
        if row is None or row.organization_id != organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework review escalation event not found")
        return row

    def _active_membership_with_role(self, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> tuple[Membership, Role]:
        membership = self.db.execute(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.user_id == user_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User must be an active organization member")
        role = self.db.execute(select(Role).where(Role.id == membership.role_id)).scalar_one_or_none()
        if role is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Membership role not found")
        return membership, role

    def _is_owner_or_admin(self, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        _, role = self._active_membership_with_role(organization_id=organization_id, user_id=user_id)
        return role.name in {"owner", "admin"}

    def _ensure_active_org_member(self, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> User:
        membership = self.db.execute(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.user_id == user_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="assigned_to_user_id must be an active member of the organization")
        user = self.db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assigned user not found")
        return user

    def _assignment_review_title(self, review: FrameworkPackReviewRun) -> str:
        return f"Framework pack review: {review.review_type} -> {review.target_coverage_level}"

    def _require_coverage_report(
        self,
        *,
        framework_id: uuid.UUID,
        coverage_report_id: uuid.UUID,
    ) -> FrameworkPackCoverageReport:
        row = self.db.execute(
            select(FrameworkPackCoverageReport).where(FrameworkPackCoverageReport.id == coverage_report_id)
        ).scalar_one_or_none()
        if row is None or row.framework_id != framework_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid coverage_report_id")
        return row

    def start_review(
        self,
        *,
        organization_id: uuid.UUID,
        framework_id: uuid.UUID,
        framework_version_id: uuid.UUID | None,
        pack_key: str | None,
        coverage_report_id: uuid.UUID | None,
        review_type: str,
        target_coverage_level: str,
        checklist_json: dict | None,
        actor_user_id: uuid.UUID,
    ) -> FrameworkPackReviewRun:
        self.require_framework(framework_id)
        self._require_review_type(review_type)
        self._require_coverage_level(target_coverage_level)

        if framework_version_id is not None:
            version = self.db.execute(select(FrameworkVersion).where(FrameworkVersion.id == framework_version_id)).scalar_one_or_none()
            if version is None or version.framework_id != framework_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid framework_version_id")

        if coverage_report_id is not None:
            self._require_coverage_report(framework_id=framework_id, coverage_report_id=coverage_report_id)

        coverage = self.pack_service.coverage_details(framework_id)
        started_at = self.now()

        row = FrameworkPackReviewRun(
            organization_id=organization_id,
            framework_id=framework_id,
            framework_version_id=framework_version_id or coverage.get("framework_version_id"),
            pack_key=pack_key or coverage.get("pack_key"),
            coverage_report_id=coverage_report_id,
            review_type=review_type,
            target_coverage_level=target_coverage_level,
            status="running",
            started_by_user_id=actor_user_id,
            started_at=started_at,
            checklist_json=checklist_json or {},
            findings_json=None,
            coverage_snapshot_json=self._json_safe(coverage),
            caveat=REVIEW_CAVEAT,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def complete_review(
        self,
        *,
        row: FrameworkPackReviewRun,
        outcome: str,
        checklist_json: dict,
        findings_json: dict | None,
        caveat: str | None,
        actor_user_id: uuid.UUID,
    ) -> FrameworkPackReviewRun:
        if row.status != "running":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Review must be running")
        self._require_outcome(outcome)

        row.status = "completed"
        row.outcome = outcome
        row.checklist_json = checklist_json
        row.findings_json = findings_json
        row.completed_by_user_id = actor_user_id
        row.completed_at = self.now()
        row.caveat = caveat.strip() if caveat and caveat.strip() else REVIEW_CAVEAT
        self.db.flush()
        return row

    def _signer_role_name(self, *, organization_id: uuid.UUID, signer_user_id: uuid.UUID) -> str | None:
        membership = self.db.execute(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.user_id == signer_user_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Signer must be an active organization member")

        role = self.db.execute(select(Role).where(Role.id == membership.role_id)).scalar_one_or_none()
        return role.name if role is not None else None

    def create_signoff(
        self,
        *,
        row: FrameworkPackReviewRun,
        signer_user_id: uuid.UUID,
        decision: str,
        comment: str | None,
    ) -> FrameworkPackReviewSignoff:
        if row.status != "completed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Review must be completed before signoff")
        decision = validate_choice(decision, SIGNOFF_DECISIONS, "decision", status_code=status.HTTP_400_BAD_REQUEST)
        existing = self.repo.get_signoff_by_signer(
            organization_id=row.organization_id,
            review_run_id=row.id,
            signer_user_id=signer_user_id,
        )
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Signer has already signed off this review")

        signer_role_name = self._signer_role_name(organization_id=row.organization_id, signer_user_id=signer_user_id)
        signed_at = self.now()
        payload = {
            "review_run_id": str(row.id),
            "organization_id": str(row.organization_id),
            "signer_user_id": str(signer_user_id),
            "signer_role_name": signer_role_name,
            "decision": decision,
            "comment": comment,
            "signed_at": signed_at.isoformat(),
        }
        checksum = self._checksum(payload)
        signature = self._signature(checksum)

        signoff = FrameworkPackReviewSignoff(
            organization_id=row.organization_id,
            review_run_id=row.id,
            signer_user_id=signer_user_id,
            signer_role_name=signer_role_name,
            decision=decision,
            comment=comment,
            signed_at=signed_at,
            signoff_checksum_sha256=checksum,
            signoff_signature=signature,
            signing_key_id=SIGNING_KEY_ID,
            signature_algorithm=INTEGRITY_ALGORITHM,
        )
        self.db.add(signoff)
        self.db.flush()
        return signoff

    def _approved_signoff_count(self, *, organization_id: uuid.UUID, review_id: uuid.UUID) -> int:
        return int(
            self.db.execute(
                select(func.count(FrameworkPackReviewSignoff.id)).where(
                    FrameworkPackReviewSignoff.organization_id == organization_id,
                    FrameworkPackReviewSignoff.review_run_id == review_id,
                    FrameworkPackReviewSignoff.decision == "approved",
                )
            ).scalar_one()
        )

    @staticmethod
    def _finding_accepts_missing_content(findings_json: dict | None) -> bool:
        if not findings_json or not isinstance(findings_json, dict):
            return False
        if findings_json.get("accept_missing_content_gaps") is True:
            return True
        accepted_gaps = findings_json.get("accepted_gaps")
        return isinstance(accepted_gaps, list) and "missing_content_count" in accepted_gaps

    def evaluate_promotion_gates(
        self,
        *,
        organization_id: uuid.UUID,
        framework_id: uuid.UUID,
        review_run_id: uuid.UUID,
        to_coverage_level: str,
    ) -> dict[str, Any]:
        framework = self.require_framework(framework_id)
        review = self.require_review(organization_id=organization_id, framework_id=framework_id, review_id=review_run_id)
        self._require_coverage_level(to_coverage_level)

        active_version = self._active_version(framework_id)
        from_coverage_level = active_version.coverage_level if active_version is not None else framework.coverage_level
        self._validate_promotion_path(from_level=from_coverage_level, to_level=to_coverage_level)

        coverage = self.pack_service.coverage_details(framework_id)
        approved_signoffs = self._approved_signoff_count(organization_id=organization_id, review_id=review.id)
        failures: list[str] = []

        if review.status != "completed":
            failures.append("review must be completed")
        if review.outcome != "pass":
            failures.append("review outcome must be pass")

        if review.coverage_report_id is None:
            failures.append("coverage report is required")
        else:
            self._require_coverage_report(framework_id=framework_id, coverage_report_id=review.coverage_report_id)

        if coverage["total_obligations"] <= 0:
            failures.append("total_obligations must be greater than zero")

        if to_coverage_level == "reviewed":
            if coverage["missing_content_count"] > 0 and not self._finding_accepts_missing_content(review.findings_json):
                failures.append("missing_content_count must be zero or explicitly accepted in findings")
            if approved_signoffs < 1:
                failures.append("at least one approved signoff is required")

        if to_coverage_level == "full_verified":
            if review.review_type != "final_verification":
                failures.append("review_type must be final_verification")
            if approved_signoffs < 2:
                failures.append("at least two approved signoffs are required")
            if coverage["missing_content_count"] > 0:
                failures.append("missing_content_count must be zero")
            if coverage["missing_evidence_requirement_count"] > 0:
                failures.append("missing_evidence_requirement_count must be zero")
            if coverage["missing_control_suggestion_count"] > 0:
                failures.append("missing_control_suggestion_count must be zero")

        return {
            "passed": len(failures) == 0,
            "gate_failures": failures,
            "from_coverage_level": from_coverage_level,
            "to_coverage_level": to_coverage_level,
            "approved_signoffs": approved_signoffs,
            "review_type": review.review_type,
            "review_outcome": review.outcome,
            "coverage": {
                "total_obligations": coverage["total_obligations"],
                "missing_content_count": coverage["missing_content_count"],
                "missing_evidence_requirement_count": coverage["missing_evidence_requirement_count"],
                "missing_control_suggestion_count": coverage["missing_control_suggestion_count"],
            },
            "caveat": REVIEW_CAVEAT,
        }

    def create_promotion_request(
        self,
        *,
        organization_id: uuid.UUID,
        framework_id: uuid.UUID,
        review_run_id: uuid.UUID,
        to_coverage_level: str,
        actor_user_id: uuid.UUID,
    ) -> FrameworkPackPromotionRequest:
        gate = self.evaluate_promotion_gates(
            organization_id=organization_id,
            framework_id=framework_id,
            review_run_id=review_run_id,
            to_coverage_level=to_coverage_level,
        )
        if not gate["passed"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Promotion gates failed", "gate_failures": gate["gate_failures"]},
            )

        review = self.require_review(organization_id=organization_id, framework_id=framework_id, review_id=review_run_id)
        requested_at = self.now()
        row = FrameworkPackPromotionRequest(
            organization_id=organization_id,
            framework_id=framework_id,
            framework_version_id=review.framework_version_id,
            review_run_id=review_run_id,
            from_coverage_level=gate["from_coverage_level"],
            to_coverage_level=to_coverage_level,
            status="pending",
            requested_by_user_id=actor_user_id,
            requested_at=requested_at,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def approve_promotion(self, *, row: FrameworkPackPromotionRequest, actor_user_id: uuid.UUID) -> FrameworkPackPromotionRequest:
        if row.status != "pending":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Promotion request is not pending")
        if row.requested_by_user_id == actor_user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requester cannot approve their own promotion request")
        row.status = "approved"
        row.approved_by_user_id = actor_user_id
        row.approved_at = self.now()
        self.db.flush()
        return row

    def reject_promotion(
        self,
        *,
        row: FrameworkPackPromotionRequest,
        actor_user_id: uuid.UUID,
        rejection_reason: str,
    ) -> FrameworkPackPromotionRequest:
        if row.status != "pending":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Promotion request is not pending")
        if not rejection_reason.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="rejection_reason is required")
        row.status = "rejected"
        row.rejected_by_user_id = actor_user_id
        row.rejected_at = self.now()
        row.rejection_reason = rejection_reason
        self.db.flush()
        return row

    def execute_promotion(self, *, row: FrameworkPackPromotionRequest, actor_user_id: uuid.UUID) -> FrameworkPackPromotionRequest:
        if row.status != "approved":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Promotion request is not approved")

        gates = self.evaluate_promotion_gates(
            organization_id=row.organization_id,
            framework_id=row.framework_id,
            review_run_id=row.review_run_id,
            to_coverage_level=row.to_coverage_level,
        )
        if not gates["passed"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Promotion gate recheck failed", "gate_failures": gates["gate_failures"]},
            )

        target_version: FrameworkVersion | None = None
        if row.framework_version_id is not None:
            target_version = self.db.execute(
                select(FrameworkVersion).where(FrameworkVersion.id == row.framework_version_id)
            ).scalar_one_or_none()
            if target_version is None or target_version.framework_id != row.framework_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Promotion target framework version not found")
        else:
            target_version = self._active_version(row.framework_id)
            if target_version is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Promotion requires an active framework version")

        before_level = target_version.coverage_level
        target_version.coverage_level = row.to_coverage_level

        row.status = "executed"
        row.executed_by_user_id = actor_user_id
        row.executed_at = self.now()
        row.execution_result_json = {
            "framework_version_id": str(target_version.id),
            "from_coverage_level": before_level,
            "to_coverage_level": row.to_coverage_level,
            "gate_recheck": gates,
            "executed_at": row.executed_at.isoformat() if row.executed_at else None,
        }
        self.db.flush()
        return row

    def create_assignment(
        self,
        *,
        organization_id: uuid.UUID,
        framework_id: uuid.UUID,
        review_id: uuid.UUID,
        assigned_to_user_id: uuid.UUID,
        assigned_by_user_id: uuid.UUID,
        due_at: datetime | None,
        notes: str | None,
        notify: bool = False,
    ) -> tuple[FrameworkPackReviewAssignment, uuid.UUID | None]:
        review = self.require_review(organization_id=organization_id, framework_id=framework_id, review_id=review_id)
        assignee = self._ensure_active_org_member(organization_id=organization_id, user_id=assigned_to_user_id)

        row = FrameworkPackReviewAssignment(
            organization_id=organization_id,
            review_run_id=review.id,
            assigned_to_user_id=assigned_to_user_id,
            assigned_by_user_id=assigned_by_user_id,
            status="assigned",
            due_at=due_at,
            notes=notes,
        )
        self.db.add(row)
        self.db.flush()

        queued_email_id: uuid.UUID | None = None
        if notify and assignee.email:
            queued_email_id = self._queue_assignment_email(
                organization_id=organization_id,
                actor_user_id=assigned_by_user_id,
                assignee=assignee,
                review=review,
                due_at=due_at,
            )
        return row, queued_email_id

    def list_assignments_for_review(
        self,
        *,
        organization_id: uuid.UUID,
        framework_id: uuid.UUID,
        review_id: uuid.UUID,
    ) -> list[FrameworkPackReviewAssignment]:
        _ = self.require_review(organization_id=organization_id, framework_id=framework_id, review_id=review_id)
        return self.repo.list_assignments_for_review(organization_id=organization_id, review_run_id=review_id)

    def list_assignments_for_org(self, *, organization_id: uuid.UUID) -> list[FrameworkPackReviewAssignment]:
        return self.repo.list_assignments_for_org(organization_id=organization_id)

    def list_assignments_for_user(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[FrameworkPackReviewAssignment]:
        return self.repo.list_assignments_for_user(organization_id=organization_id, assigned_to_user_id=user_id)

    def _ensure_assignment_actor_can_update(
        self,
        *,
        assignment: FrameworkPackReviewAssignment,
        actor_user_id: uuid.UUID,
    ) -> None:
        if assignment.assigned_to_user_id == actor_user_id:
            return
        if self._is_owner_or_admin(organization_id=assignment.organization_id, user_id=actor_user_id):
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only assigned reviewer or owner/admin can perform this action")

    def accept_assignment(
        self,
        *,
        assignment: FrameworkPackReviewAssignment,
        actor_user_id: uuid.UUID,
    ) -> FrameworkPackReviewAssignment:
        self._ensure_assignment_actor_can_update(assignment=assignment, actor_user_id=actor_user_id)
        if assignment.status not in {"assigned", "overdue"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assignment cannot be accepted from current status")
        assignment.status = "accepted"
        if assignment.accepted_at is None:
            assignment.accepted_at = self.now()
        self.db.flush()
        return assignment

    def complete_assignment(
        self,
        *,
        assignment: FrameworkPackReviewAssignment,
        actor_user_id: uuid.UUID,
        notes: str | None,
    ) -> FrameworkPackReviewAssignment:
        self._ensure_assignment_actor_can_update(assignment=assignment, actor_user_id=actor_user_id)
        if assignment.status in {"completed", "cancelled"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assignment cannot be completed from current status")
        assignment.status = "completed"
        assignment.completed_at = self.now()
        if notes and notes.strip():
            assignment.notes = notes.strip()
        self.db.flush()
        return assignment

    def cancel_assignment(
        self,
        *,
        assignment: FrameworkPackReviewAssignment,
        reason: str,
    ) -> FrameworkPackReviewAssignment:
        if assignment.status in {"completed", "cancelled"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assignment cannot be cancelled from current status")
        if not reason.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="reason is required")
        assignment.status = "cancelled"
        assignment.cancelled_at = self.now()
        assignment.notes = reason.strip()
        self.db.flush()
        return assignment

    @staticmethod
    def _validate_non_negative(name: str, value: int) -> None:
        if value < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{name} must be non-negative")

    def create_sla_policy(
        self,
        *,
        organization_id: uuid.UUID,
        name: str,
        review_type: str,
        target_coverage_level: str | None,
        due_days: int,
        escalation_after_days: int,
        reminder_before_days: int,
        status_value: str,
        actor_user_id: uuid.UUID,
    ) -> FrameworkReviewSLAPolicy:
        self._require_review_type(review_type)
        if target_coverage_level is not None:
            self._require_coverage_level(target_coverage_level)
        self._validate_non_negative("due_days", due_days)
        self._validate_non_negative("escalation_after_days", escalation_after_days)
        self._validate_non_negative("reminder_before_days", reminder_before_days)
        status_value = validate_choice(status_value, SLA_POLICY_STATUSES, "SLA policy status", status_code=status.HTTP_400_BAD_REQUEST)
        row = FrameworkReviewSLAPolicy(
            organization_id=organization_id,
            name=name.strip(),
            review_type=review_type,
            target_coverage_level=target_coverage_level,
            due_days=due_days,
            escalation_after_days=escalation_after_days,
            reminder_before_days=reminder_before_days,
            status=status_value,
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def update_sla_policy(
        self,
        *,
        row: FrameworkReviewSLAPolicy,
        name: str | None = None,
        review_type: str | None = None,
        target_coverage_level: str | None = None,
        due_days: int | None = None,
        escalation_after_days: int | None = None,
        reminder_before_days: int | None = None,
        status_value: str | None = None,
    ) -> FrameworkReviewSLAPolicy:
        if review_type is not None:
            self._require_review_type(review_type)
            row.review_type = review_type
        if target_coverage_level is not None:
            self._require_coverage_level(target_coverage_level)
            row.target_coverage_level = target_coverage_level
        if name is not None:
            row.name = name.strip()
        if due_days is not None:
            self._validate_non_negative("due_days", due_days)
            row.due_days = due_days
        if escalation_after_days is not None:
            self._validate_non_negative("escalation_after_days", escalation_after_days)
            row.escalation_after_days = escalation_after_days
        if reminder_before_days is not None:
            self._validate_non_negative("reminder_before_days", reminder_before_days)
            row.reminder_before_days = reminder_before_days
        if status_value is not None:
            status_value = validate_choice(status_value, SLA_POLICY_STATUSES, "SLA policy status", status_code=status.HTTP_400_BAD_REQUEST)
            row.status = status_value
        self.db.flush()
        return row

    def archive_sla_policy(self, *, row: FrameworkReviewSLAPolicy) -> FrameworkReviewSLAPolicy:
        if row.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SLA policy is already archived")
        row.status = "archived"
        self.db.flush()
        return row

    def list_sla_policies(self, *, organization_id: uuid.UUID) -> list[FrameworkReviewSLAPolicy]:
        return self.repo.list_sla_policies(organization_id=organization_id)

    def list_escalation_events(self, *, organization_id: uuid.UUID) -> list[FrameworkReviewEscalationEvent]:
        return self.repo.list_escalation_events(organization_id=organization_id)

    def _matching_sla_policy(
        self,
        *,
        organization_id: uuid.UUID,
        review: FrameworkPackReviewRun,
    ) -> FrameworkReviewSLAPolicy | None:
        policies = [
            item
            for item in self.repo.list_sla_policies(organization_id=organization_id)
            if item.status == "active" and item.review_type == review.review_type
        ]
        exact = [item for item in policies if item.target_coverage_level == review.target_coverage_level]
        if exact:
            return exact[0]
        fallback = [item for item in policies if item.target_coverage_level is None]
        return fallback[0] if fallback else None

    def _find_open_escalation(
        self,
        *,
        organization_id: uuid.UUID,
        review_run_id: uuid.UUID,
        assignment_id: uuid.UUID | None,
        event_type: str,
    ) -> FrameworkReviewEscalationEvent | None:
        return self.db.execute(
            select(FrameworkReviewEscalationEvent).where(
                FrameworkReviewEscalationEvent.organization_id == organization_id,
                FrameworkReviewEscalationEvent.review_run_id == review_run_id,
                FrameworkReviewEscalationEvent.assignment_id == assignment_id,
                FrameworkReviewEscalationEvent.event_type == event_type,
                FrameworkReviewEscalationEvent.status == "open",
            )
        ).scalar_one_or_none()

    def _create_escalation(
        self,
        *,
        organization_id: uuid.UUID,
        review_run_id: uuid.UUID,
        assignment_id: uuid.UUID | None,
        event_type: str,
        details_json: dict | None,
    ) -> FrameworkReviewEscalationEvent:
        event_type = validate_choice(event_type, ESCALATION_TYPES, "escalation event type", status_code=status.HTTP_400_BAD_REQUEST)
        existing = self._find_open_escalation(
            organization_id=organization_id,
            review_run_id=review_run_id,
            assignment_id=assignment_id,
            event_type=event_type,
        )
        if existing is not None:
            return existing
        row = FrameworkReviewEscalationEvent(
            organization_id=organization_id,
            review_run_id=review_run_id,
            assignment_id=assignment_id,
            event_type=event_type,
            status="open",
            triggered_at=self.now(),
            details_json=details_json,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _queue_assignment_email(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        assignee: User,
        review: FrameworkPackReviewRun,
        due_at: datetime | None,
    ) -> uuid.UUID | None:
        if not assignee.email:
            return None
        SeedService.ensure_global_email_templates(self.db)
        template = EmailService(self.db).resolve_template_for_org(
            organization_id=organization_id,
            template_id=None,
            template_key="task_assigned",
        )
        outbox = EmailService(self.db).queue_email(
            organization_id=organization_id,
            template=template,
            event_type="framework.review.assignment",
            recipient_email=assignee.email,
            recipient_user_id=assignee.id,
            priority="normal",
            scheduled_at=None,
            metadata_json={"source": "framework_review_assignment"},
            created_by_user_id=actor_user_id,
            variables_json={
                "user_name": assignee.full_name or assignee.email,
                "task_title": f"{self._assignment_review_title(review)} (due: {due_at.isoformat() if due_at else 'unspecified'})",
            },
            initial_status="pending",
        )
        return outbox.id

    def _queue_sla_reminder_email(
        self,
        *,
        assignment: FrameworkPackReviewAssignment,
        review: FrameworkPackReviewRun,
        actor_user_id: uuid.UUID,
    ) -> uuid.UUID | None:
        assignee = self.db.execute(select(User).where(User.id == assignment.assigned_to_user_id)).scalar_one_or_none()
        if assignee is None or not assignee.email:
            return None
        SeedService.ensure_global_email_templates(self.db)
        template = EmailService(self.db).resolve_template_for_org(
            organization_id=assignment.organization_id,
            template_id=None,
            template_key="task_assigned",
        )
        outbox = EmailService(self.db).queue_email(
            organization_id=assignment.organization_id,
            template=template,
            event_type="framework.review.sla_reminder",
            recipient_email=assignee.email,
            recipient_user_id=assignee.id,
            priority="normal",
            scheduled_at=None,
            metadata_json={"source": "framework_review_sla"},
            created_by_user_id=actor_user_id,
            variables_json={
                "user_name": assignee.full_name or assignee.email,
                "task_title": f"{self._assignment_review_title(review)} (assignment due {assignment.due_at.isoformat() if assignment.due_at else 'unspecified'})",
            },
            initial_status="pending",
        )
        return outbox.id

    def evaluate_sla(
        self,
        *,
        organization_id: uuid.UUID,
        dry_run: bool,
        notify: bool,
        actor_user_id: uuid.UUID,
    ) -> dict[str, Any]:
        now = self.now()
        assignments = self.repo.list_assignments_for_org(organization_id=organization_id)
        review_rows = self.db.execute(
            select(FrameworkPackReviewRun).where(FrameworkPackReviewRun.organization_id == organization_id)
        ).scalars().all()
        reviews = {row.id: row for row in review_rows}
        promotions = self.db.execute(
            select(FrameworkPackPromotionRequest).where(FrameworkPackPromotionRequest.organization_id == organization_id)
        ).scalars().all()

        would_create: list[dict[str, Any]] = []
        created_events: list[FrameworkReviewEscalationEvent] = []
        queued_email_ids: list[str] = []

        for assignment in assignments:
            if assignment.status in {"completed", "cancelled"}:
                continue
            review = reviews.get(assignment.review_run_id)
            if review is None:
                continue
            policy = self._matching_sla_policy(organization_id=organization_id, review=review)
            if policy is None:
                continue
            due_at_raw = assignment.due_at or (review.started_at + timedelta(days=policy.due_days))
            due_at = self._ensure_utc(due_at_raw)
            reminder_at = due_at - timedelta(days=policy.reminder_before_days)
            escalation_at = due_at + timedelta(days=policy.escalation_after_days)

            reminder_due = now >= reminder_at and now <= due_at
            overdue = now > due_at or now >= escalation_at

            if reminder_due:
                payload = {
                    "event_type": "reminder_due",
                    "review_run_id": str(review.id),
                    "assignment_id": str(assignment.id),
                    "due_at": due_at.isoformat(),
                }
                if dry_run:
                    would_create.append(payload)
                else:
                    event = self._create_escalation(
                        organization_id=organization_id,
                        review_run_id=review.id,
                        assignment_id=assignment.id,
                        event_type="reminder_due",
                        details_json=payload,
                    )
                    created_events.append(event)
                    if notify:
                        email_id = self._queue_sla_reminder_email(assignment=assignment, review=review, actor_user_id=actor_user_id)
                        if email_id is not None:
                            queued_email_ids.append(str(email_id))

            if overdue:
                payload = {
                    "event_type": "review_overdue",
                    "review_run_id": str(review.id),
                    "assignment_id": str(assignment.id),
                    "due_at": due_at.isoformat(),
                    "status_before": assignment.status,
                }
                if dry_run:
                    would_create.append(payload)
                else:
                    if assignment.status in {"assigned", "accepted"}:
                        assignment.status = "overdue"
                    event = self._create_escalation(
                        organization_id=organization_id,
                        review_run_id=review.id,
                        assignment_id=assignment.id,
                        event_type="review_overdue",
                        details_json=payload,
                    )
                    created_events.append(event)

        for review in review_rows:
            policy = self._matching_sla_policy(organization_id=organization_id, review=review)
            if policy is None:
                continue
            signoff_count = self._approved_signoff_count(organization_id=organization_id, review_id=review.id)
            if review.status == "completed" and signoff_count == 0 and review.completed_at is not None:
                completed_at = self._ensure_utc(review.completed_at)
                if now >= completed_at + timedelta(days=policy.escalation_after_days):
                    payload = {
                        "event_type": "signoff_missing",
                        "review_run_id": str(review.id),
                        "completed_at": completed_at.isoformat(),
                    }
                    if dry_run:
                        would_create.append(payload)
                    else:
                        created_events.append(
                            self._create_escalation(
                                organization_id=organization_id,
                                review_run_id=review.id,
                                assignment_id=None,
                                event_type="signoff_missing",
                                details_json=payload,
                            )
                        )

        for promotion in promotions:
            if promotion.status != "pending":
                continue
            review = reviews.get(promotion.review_run_id)
            if review is None:
                continue
            policy = self._matching_sla_policy(organization_id=organization_id, review=review)
            if policy is None:
                continue
            requested_at = self._ensure_utc(promotion.requested_at)
            if now >= requested_at + timedelta(days=policy.escalation_after_days):
                payload = {
                    "event_type": "promotion_pending_too_long",
                    "review_run_id": str(review.id),
                    "promotion_id": str(promotion.id),
                    "requested_at": requested_at.isoformat(),
                }
                if dry_run:
                    would_create.append(payload)
                else:
                    created_events.append(
                        self._create_escalation(
                            organization_id=organization_id,
                            review_run_id=review.id,
                            assignment_id=None,
                            event_type="promotion_pending_too_long",
                            details_json=payload,
                        )
                    )

        if not dry_run:
            self.db.flush()
        return {
            "dry_run": dry_run,
            "would_create_count": len(would_create),
            "created_count": 0 if dry_run else len(created_events),
            "queued_email_count": 0 if dry_run else len(queued_email_ids),
            "would_create": would_create,
            "created_event_ids": [] if dry_run else [str(row.id) for row in created_events],
            "queued_email_ids": [] if dry_run else queued_email_ids,
        }

    def resolve_escalation_event(
        self,
        *,
        row: FrameworkReviewEscalationEvent,
        resolution_notes: str | None,
    ) -> FrameworkReviewEscalationEvent:
        if row.status != "open":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Escalation event is not open")
        row.status = "resolved"
        row.resolved_at = self.now()
        details = dict(row.details_json or {})
        if resolution_notes and resolution_notes.strip():
            details["resolution_notes"] = resolution_notes.strip()
        row.details_json = details
        self.db.flush()
        return row

    def review_queue_summary(self, *, organization_id: uuid.UUID) -> dict[str, int]:
        now = self.now()
        assignments = self.repo.list_assignments_for_org(organization_id=organization_id)
        escalation_events = self.repo.list_escalation_events(organization_id=organization_id)
        review_rows = self.db.execute(
            select(FrameworkPackReviewRun).where(FrameworkPackReviewRun.organization_id == organization_id)
        ).scalars().all()
        promotions = self.db.execute(
            select(FrameworkPackPromotionRequest).where(FrameworkPackPromotionRequest.organization_id == organization_id)
        ).scalars().all()

        overdue_count = len(
            [
                row
                for row in assignments
                if row.status == "overdue"
                or (
                    row.status in {"assigned", "accepted"}
                    and row.due_at is not None
                    and self._ensure_utc(row.due_at) < now
                )
            ]
        )
        waiting_signoff = 0
        for review in review_rows:
            if review.status != "completed":
                continue
            if self._approved_signoff_count(organization_id=organization_id, review_id=review.id) == 0:
                waiting_signoff += 1

        return {
            "total_assignments": len(assignments),
            "open_assignments": len([row for row in assignments if row.status == "assigned"]),
            "accepted_assignments": len([row for row in assignments if row.status == "accepted"]),
            "completed_assignments": len([row for row in assignments if row.status == "completed"]),
            "overdue_assignments": overdue_count,
            "open_escalations": len([row for row in escalation_events if row.status == "open"]),
            "reviews_waiting_for_signoff": waiting_signoff,
            "promotions_pending_approval": len([row for row in promotions if row.status == "pending"]),
        }

    def review_summary(self, *, organization_id: uuid.UUID, framework_id: uuid.UUID) -> dict[str, Any]:
        reviews = self.repo.list_reviews(organization_id=organization_id, framework_id=framework_id)
        promotions = self.repo.list_promotions(organization_id=organization_id, framework_id=framework_id)
        latest = reviews[0] if reviews else None

        approved_signoffs = (
            self._approved_signoff_count(organization_id=organization_id, review_id=latest.id) if latest is not None else 0
        )

        framework = self.require_framework(framework_id)
        active_version = self._active_version(framework_id)
        current_level = active_version.coverage_level if active_version is not None else framework.coverage_level
        next_level = self._next_level(current_level)

        readiness = {
            "next_target_coverage_level": next_level,
            "ready": False,
            "gate_failures": ["no next coverage level"] if next_level is None else ["no completed review available"],
        }
        if latest is not None and next_level is not None:
            gate = self.evaluate_promotion_gates(
                organization_id=organization_id,
                framework_id=framework_id,
                review_run_id=latest.id,
                to_coverage_level=next_level,
            )
            readiness = {
                "next_target_coverage_level": next_level,
                "ready": gate["passed"],
                "gate_failures": gate["gate_failures"],
            }

        return {
            "latest_review_status": latest.status if latest else None,
            "latest_review_outcome": latest.outcome if latest else None,
            "latest_review_type": latest.review_type if latest else None,
            "approved_signoffs": approved_signoffs,
            "pending_promotions": len([row for row in promotions if row.status == "pending"]),
            "executed_promotions": len([row for row in promotions if row.status == "executed"]),
            "current_coverage_level": current_level,
            "promotion_readiness": readiness,
            "caveat": REVIEW_CAVEAT,
        }
