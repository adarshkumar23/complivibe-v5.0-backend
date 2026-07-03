import uuid
import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.framework_pack_review_assignment import FrameworkPackReviewAssignment
from app.models.framework_pack_review_run import FrameworkPackReviewRun
from app.models.audit_log import AuditLog
from app.models.framework_review_assignment_suggestion import FrameworkReviewAssignmentSuggestion
from app.models.framework_review_escalation_event import FrameworkReviewEscalationEvent
from app.models.framework_review_batch_cancellation_request import FrameworkReviewBatchCancellationRequest
from app.models.framework_review_batch_assignment_item import FrameworkReviewBatchAssignmentItem
from app.models.framework_review_batch_assignment_run import FrameworkReviewBatchAssignmentRun
from app.models.framework_reviewer_capacity_policy import FrameworkReviewerCapacityPolicy
from app.models.framework_reviewer_workload_snapshot import FrameworkReviewerWorkloadSnapshot
from app.models.membership import Membership
from app.models.organization_governance_setting import OrganizationGovernanceSetting
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.repositories.framework_review_capacity_repository import FrameworkReviewCapacityRepository
from app.services.framework_pack_review_service import FrameworkPackReviewService
from app.core.validation import validate_choice

CAPACITY_POLICY_STATUSES = {"active", "inactive", "archived"}
_OPEN_ASSIGNMENT_STATUSES = {"assigned", "accepted", "overdue"}
SIMULATION_CAVEAT = (
    "This simulation is deterministic and preview-only. "
    "It does not create assignments, persist suggestions, or change reviewer workload."
)
WAVE_SIMULATION_CAVEAT = (
    "This is a deterministic planning preview. "
    "It does not create assignments, persist suggestions, change workload snapshots, or send notifications."
)
SIMULATION_PROVENANCE = "deterministic_policy_simulation_v1"
BATCH_ASSIGNMENT_CONFIRMATION_TEXT = "CONFIRM_BATCH_ASSIGNMENTS"
BATCH_ASSIGNMENT_CAVEAT = (
    "This batch assignment workflow is deterministic and requires explicit confirmation. "
    "It does not auto-assign reviews without the apply endpoint."
)
BATCH_CANCELLATION_APPROVAL_REQUIRED_DETAIL = (
    "Cancellation requires approval. Create a cancellation request instead."
)


class FrameworkReviewCapacityService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = FrameworkReviewCapacityRepository(db)
        self.review_service = FrameworkPackReviewService(db)

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
    def _validate_non_negative(name: str, value: int) -> None:
        if value < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{name} must be non-negative")

    @staticmethod
    def _validate_policy_status(value: str) -> None:
        value = validate_choice(value, CAPACITY_POLICY_STATUSES, "capacity policy status", status_code=status.HTTP_400_BAD_REQUEST)
    @staticmethod
    def _normalize_optional_list(value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned: list[str] = []
        for item in value:
            token = item.strip()
            if token and token not in cleaned:
                cleaned.append(token)
        return cleaned if cleaned else None

    @staticmethod
    def _normalized_name(name: str) -> str:
        cleaned = name.strip()
        if not cleaned:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name is required")
        return cleaned

    def require_capacity_policy(self, *, organization_id: uuid.UUID, policy_id: uuid.UUID) -> FrameworkReviewerCapacityPolicy:
        row = self.repo.get_capacity_policy(policy_id)
        if row is None or row.organization_id != organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework reviewer capacity policy not found")
        return row

    def require_assignment_suggestion(
        self,
        *,
        organization_id: uuid.UUID,
        suggestion_id: uuid.UUID,
    ) -> FrameworkReviewAssignmentSuggestion:
        row = self.repo.get_assignment_suggestion(suggestion_id)
        if row is None or row.organization_id != organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework review assignment suggestion not found")
        return row

    def create_capacity_policy(
        self,
        *,
        organization_id: uuid.UUID,
        name: str,
        role_name: str | None,
        max_active_assignments: int,
        max_overdue_assignments: int,
        preferred_review_types_json: list[str] | None,
        preferred_target_coverage_levels_json: list[str] | None,
        status_value: str,
        actor_user_id: uuid.UUID,
    ) -> FrameworkReviewerCapacityPolicy:
        self._validate_non_negative("max_active_assignments", max_active_assignments)
        self._validate_non_negative("max_overdue_assignments", max_overdue_assignments)
        self._validate_policy_status(status_value)

        row = FrameworkReviewerCapacityPolicy(
            organization_id=organization_id,
            name=self._normalized_name(name),
            role_name=role_name.strip() if role_name and role_name.strip() else None,
            max_active_assignments=max_active_assignments,
            max_overdue_assignments=max_overdue_assignments,
            preferred_review_types_json=self._normalize_optional_list(preferred_review_types_json),
            preferred_target_coverage_levels_json=self._normalize_optional_list(preferred_target_coverage_levels_json),
            status=status_value,
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_capacity_policies(self, *, organization_id: uuid.UUID) -> list[FrameworkReviewerCapacityPolicy]:
        return self.repo.list_capacity_policies(organization_id=organization_id)

    def update_capacity_policy(
        self,
        *,
        row: FrameworkReviewerCapacityPolicy,
        name: str | None,
        role_name: str | None,
        max_active_assignments: int | None,
        max_overdue_assignments: int | None,
        preferred_review_types_json: list[str] | None,
        preferred_target_coverage_levels_json: list[str] | None,
        status_value: str | None,
    ) -> FrameworkReviewerCapacityPolicy:
        if name is not None:
            row.name = self._normalized_name(name)
        if role_name is not None:
            row.role_name = role_name.strip() if role_name.strip() else None
        if max_active_assignments is not None:
            self._validate_non_negative("max_active_assignments", max_active_assignments)
            row.max_active_assignments = max_active_assignments
        if max_overdue_assignments is not None:
            self._validate_non_negative("max_overdue_assignments", max_overdue_assignments)
            row.max_overdue_assignments = max_overdue_assignments
        if preferred_review_types_json is not None:
            row.preferred_review_types_json = self._normalize_optional_list(preferred_review_types_json)
        if preferred_target_coverage_levels_json is not None:
            row.preferred_target_coverage_levels_json = self._normalize_optional_list(preferred_target_coverage_levels_json)
        if status_value is not None:
            self._validate_policy_status(status_value)
            row.status = status_value
        self.db.flush()
        return row

    def archive_capacity_policy(self, *, row: FrameworkReviewerCapacityPolicy) -> FrameworkReviewerCapacityPolicy:
        if row.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Capacity policy is already archived")
        row.status = "archived"
        self.db.flush()
        return row

    def _active_policies(self, *, organization_id: uuid.UUID) -> list[FrameworkReviewerCapacityPolicy]:
        return [
            item
            for item in self.repo.list_capacity_policies(organization_id=organization_id)
            if item.status == "active"
        ]

    def _matching_policy(
        self,
        *,
        role_name: str,
        active_policies: list[FrameworkReviewerCapacityPolicy],
    ) -> FrameworkReviewerCapacityPolicy | None:
        minimum_time = datetime.min.replace(tzinfo=UTC)
        sorted_policies = sorted(
            active_policies,
            key=lambda item: (item.updated_at or minimum_time, item.created_at or minimum_time),
            reverse=True,
        )
        exact = [item for item in sorted_policies if item.role_name == role_name]
        if exact:
            return exact[0]
        generic = [item for item in sorted_policies if item.role_name is None]
        return generic[0] if generic else None

    def _build_proposed_policy(
        self,
        *,
        organization_id: uuid.UUID,
        role_name: str | None,
        max_active_assignments: int,
        max_overdue_assignments: int,
        preferred_review_types_json: list[str] | None,
        preferred_target_coverage_levels_json: list[str] | None,
        now: datetime,
    ) -> FrameworkReviewerCapacityPolicy:
        self._validate_non_negative("max_active_assignments", max_active_assignments)
        self._validate_non_negative("max_overdue_assignments", max_overdue_assignments)
        return FrameworkReviewerCapacityPolicy(
            organization_id=organization_id,
            name="simulation_policy_preview",
            role_name=role_name.strip() if role_name and role_name.strip() else None,
            max_active_assignments=max_active_assignments,
            max_overdue_assignments=max_overdue_assignments,
            preferred_review_types_json=self._normalize_optional_list(preferred_review_types_json),
            preferred_target_coverage_levels_json=self._normalize_optional_list(preferred_target_coverage_levels_json),
            status="active",
            created_at=now,
            updated_at=now,
        )

    def _matching_policy_with_override(
        self,
        *,
        role_name: str,
        active_policies: list[FrameworkReviewerCapacityPolicy],
        proposed_policy_override: FrameworkReviewerCapacityPolicy | None,
    ) -> FrameworkReviewerCapacityPolicy | None:
        if proposed_policy_override is not None and (
            proposed_policy_override.role_name is None or proposed_policy_override.role_name == role_name
        ):
            return proposed_policy_override
        return self._matching_policy(role_name=role_name, active_policies=active_policies)

    def _eligible_reviewers(self, *, organization_id: uuid.UUID) -> list[dict[str, Any]]:
        rows = self.db.execute(
            select(Membership.user_id, Role.name)
            .join(Role, Role.id == Membership.role_id)
            .join(RolePermission, RolePermission.role_id == Role.id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(
                Membership.organization_id == organization_id,
                Membership.status == "active",
                Role.organization_id == organization_id,
                Permission.key == "framework_content:review",
            )
            .distinct()
            .order_by(Membership.user_id.asc())
        ).all()
        return [{"user_id": row[0], "role_name": row[1]} for row in rows]

    def _assignment_stats(
        self,
        *,
        organization_id: uuid.UUID,
        user_ids: list[uuid.UUID],
        now: datetime,
    ) -> dict[uuid.UUID, dict[str, int]]:
        stats = {
            user_id: {
                "active_assignments": 0,
                "accepted_assignments": 0,
                "overdue_assignments": 0,
                "completed_assignments_last_30d": 0,
                "open_escalations": 0,
            }
            for user_id in user_ids
        }
        if not user_ids:
            return stats

        assignments = self.db.execute(
            select(FrameworkPackReviewAssignment).where(
                FrameworkPackReviewAssignment.organization_id == organization_id,
                FrameworkPackReviewAssignment.assigned_to_user_id.in_(user_ids),
            )
        ).scalars().all()
        completed_since = now - timedelta(days=30)
        for row in assignments:
            user_stats = stats.get(row.assigned_to_user_id)
            if user_stats is None:
                continue
            due_at = self._ensure_utc(row.due_at) if row.due_at else None
            is_overdue = row.status == "overdue" or (
                row.status in {"assigned", "accepted"} and due_at is not None and due_at < now
            )
            if row.status in _OPEN_ASSIGNMENT_STATUSES:
                user_stats["active_assignments"] += 1
            if row.status == "accepted":
                user_stats["accepted_assignments"] += 1
            if is_overdue:
                user_stats["overdue_assignments"] += 1
            if row.status == "completed" and row.completed_at is not None and self._ensure_utc(row.completed_at) >= completed_since:
                user_stats["completed_assignments_last_30d"] += 1

        escalation_rows = self.db.execute(
            select(FrameworkReviewEscalationEvent.assignment_id, FrameworkPackReviewAssignment.assigned_to_user_id)
            .join(
                FrameworkPackReviewAssignment,
                FrameworkPackReviewAssignment.id == FrameworkReviewEscalationEvent.assignment_id,
            )
            .where(
                FrameworkReviewEscalationEvent.organization_id == organization_id,
                FrameworkReviewEscalationEvent.status == "open",
                FrameworkPackReviewAssignment.organization_id == organization_id,
                FrameworkPackReviewAssignment.assigned_to_user_id.in_(user_ids),
            )
        ).all()
        for _, assigned_to_user_id in escalation_rows:
            stats[assigned_to_user_id]["open_escalations"] += 1

        return stats

    @staticmethod
    def _bounded_score(value: int) -> int:
        return max(0, min(100, value))

    def _workload_score(self, *, active: int, overdue: int, escalations: int, completed_last_30d: int) -> int:
        completed_bonus = min(15, completed_last_30d)
        raw = 100 - (active * 10) - (overdue * 25) - (escalations * 15) + completed_bonus
        return self._bounded_score(raw)

    def _capacity_remaining(
        self,
        *,
        policy: FrameworkReviewerCapacityPolicy | None,
        active_assignments: int,
        overdue_assignments: int,
    ) -> int | None:
        if policy is None:
            return None
        return min(
            policy.max_active_assignments - active_assignments,
            policy.max_overdue_assignments - overdue_assignments,
        )

    def calculate_workload(
        self,
        *,
        organization_id: uuid.UUID,
        persist: bool,
    ) -> list[FrameworkReviewerWorkloadSnapshot]:
        now = self.now()
        reviewers = self._eligible_reviewers(organization_id=organization_id)
        active_policies = self._active_policies(organization_id=organization_id)
        user_ids = [item["user_id"] for item in reviewers]
        stats = self._assignment_stats(organization_id=organization_id, user_ids=user_ids, now=now)

        rows: list[FrameworkReviewerWorkloadSnapshot] = []
        for reviewer in reviewers:
            user_id = reviewer["user_id"]
            role_name = reviewer["role_name"]
            reviewer_stats = stats.get(user_id, {})
            active_assignments = int(reviewer_stats.get("active_assignments", 0))
            accepted_assignments = int(reviewer_stats.get("accepted_assignments", 0))
            overdue_assignments = int(reviewer_stats.get("overdue_assignments", 0))
            completed_assignments_last_30d = int(reviewer_stats.get("completed_assignments_last_30d", 0))
            open_escalations = int(reviewer_stats.get("open_escalations", 0))

            policy = self._matching_policy(role_name=role_name, active_policies=active_policies)
            workload_score = self._workload_score(
                active=active_assignments,
                overdue=overdue_assignments,
                escalations=open_escalations,
                completed_last_30d=completed_assignments_last_30d,
            )
            capacity_remaining = self._capacity_remaining(
                policy=policy,
                active_assignments=active_assignments,
                overdue_assignments=overdue_assignments,
            )

            snapshot_json = {
                "role_name": role_name,
                "scoring_rule": {
                    "base": 100,
                    "active_penalty_per_assignment": 10,
                    "overdue_penalty_per_assignment": 25,
                    "open_escalation_penalty": 15,
                    "completed_bonus_cap": 15,
                },
                "policy": {
                    "id": str(policy.id) if policy else None,
                    "role_name": policy.role_name if policy else None,
                    "max_active_assignments": policy.max_active_assignments if policy else None,
                    "max_overdue_assignments": policy.max_overdue_assignments if policy else None,
                    "preferred_review_types_json": policy.preferred_review_types_json if policy else None,
                    "preferred_target_coverage_levels_json": policy.preferred_target_coverage_levels_json if policy else None,
                },
                "provenance": "deterministic_policy_scoring_v1",
            }

            row = FrameworkReviewerWorkloadSnapshot(
                organization_id=organization_id,
                user_id=user_id,
                active_assignments=active_assignments,
                accepted_assignments=accepted_assignments,
                overdue_assignments=overdue_assignments,
                completed_assignments_last_30d=completed_assignments_last_30d,
                open_escalations=open_escalations,
                workload_score=workload_score,
                capacity_remaining=capacity_remaining,
                snapshot_json=snapshot_json,
                calculated_at=now,
            )
            if persist:
                self.db.add(row)
            rows.append(row)

        if persist:
            self.db.flush()
        return rows

    def list_workload(self, *, organization_id: uuid.UUID) -> list[FrameworkReviewerWorkloadSnapshot]:
        calculated_rows = self.calculate_workload(organization_id=organization_id, persist=False)
        latest_persisted = self.repo.list_latest_workload_snapshots(organization_id=organization_id)
        persisted_map = {item.user_id: item for item in latest_persisted}
        for row in calculated_rows:
            persisted = persisted_map.get(row.user_id)
            row.snapshot_json = {
                **(row.snapshot_json or {}),
                "latest_persisted_calculated_at": persisted.calculated_at.isoformat() if persisted else None,
            }
        return calculated_rows

    def _score_reviewer(
        self,
        *,
        review: FrameworkPackReviewRun,
        reviewer: dict[str, Any],
        reviewer_stats: dict[str, int],
        policy: FrameworkReviewerCapacityPolicy | None,
    ) -> tuple[int, str, dict[str, Any]]:
        base = 100
        active_assignments = reviewer_stats["active_assignments"]
        overdue_assignments = reviewer_stats["overdue_assignments"]
        open_escalations = reviewer_stats["open_escalations"]
        completed_assignments_last_30d = reviewer_stats["completed_assignments_last_30d"]

        completed_bonus = min(15, completed_assignments_last_30d)
        role_match_bonus = 10 if policy is not None and policy.role_name == reviewer["role_name"] else 0
        preferred_review_type_bonus = (
            10
            if policy is not None
            and policy.preferred_review_types_json is not None
            and review.review_type in policy.preferred_review_types_json
            else 0
        )
        preferred_target_level_bonus = (
            10
            if policy is not None
            and policy.preferred_target_coverage_levels_json is not None
            and review.target_coverage_level in policy.preferred_target_coverage_levels_json
            else 0
        )

        capacity_active_penalty = (
            20
            if policy is not None and active_assignments > policy.max_active_assignments
            else 0
        )
        capacity_overdue_penalty = (
            35
            if policy is not None and overdue_assignments > policy.max_overdue_assignments
            else 0
        )

        raw_score = (
            base
            - (active_assignments * 10)
            - (overdue_assignments * 25)
            - (open_escalations * 15)
            + completed_bonus
            + role_match_bonus
            + preferred_review_type_bonus
            + preferred_target_level_bonus
            - capacity_active_penalty
            - capacity_overdue_penalty
        )
        final_score = self._bounded_score(raw_score)

        scoring_json = {
            "algorithm": "deterministic_policy_scoring_v1",
            "inputs": {
                "review_type": review.review_type,
                "target_coverage_level": review.target_coverage_level,
                "role_name": reviewer["role_name"],
                "active_assignments": active_assignments,
                "overdue_assignments": overdue_assignments,
                "open_escalations": open_escalations,
                "completed_assignments_last_30d": completed_assignments_last_30d,
                "policy_id": str(policy.id) if policy else None,
            },
            "weights": {
                "base": 100,
                "active_assignment_penalty": 10,
                "overdue_assignment_penalty": 25,
                "open_escalation_penalty": 15,
                "completed_last_30d_bonus_cap": 15,
                "role_match_bonus": 10,
                "preferred_review_type_bonus": 10,
                "preferred_target_coverage_level_bonus": 10,
                "capacity_active_exceeded_penalty": 20,
                "capacity_overdue_exceeded_penalty": 35,
            },
            "breakdown": {
                "base": base,
                "active_penalty": active_assignments * 10,
                "overdue_penalty": overdue_assignments * 25,
                "open_escalation_penalty": open_escalations * 15,
                "completed_bonus": completed_bonus,
                "role_match_bonus": role_match_bonus,
                "preferred_review_type_bonus": preferred_review_type_bonus,
                "preferred_target_coverage_level_bonus": preferred_target_level_bonus,
                "capacity_active_penalty": capacity_active_penalty,
                "capacity_overdue_penalty": capacity_overdue_penalty,
                "raw_score": raw_score,
                "final_score": final_score,
            },
        }
        rationale = (
            f"base=100 -active({active_assignments}*10) -overdue({overdue_assignments}*25) "
            f"-escalations({open_escalations}*15) +completed_bonus({completed_bonus}) "
            f"+role_match({role_match_bonus}) +review_type_match({preferred_review_type_bonus}) "
            f"+target_level_match({preferred_target_level_bonus}) -capacity_active_penalty({capacity_active_penalty}) "
            f"-capacity_overdue_penalty({capacity_overdue_penalty}) => {final_score}"
        )
        return final_score, rationale, scoring_json

    @staticmethod
    def scoring_formula() -> dict[str, Any]:
        return {
            "algorithm": "deterministic_policy_scoring_v1",
            "base": 100,
            "penalties": {
                "active_assignment": 10,
                "overdue_assignment": 25,
                "open_escalation": 15,
                "capacity_active_exceeded": 20,
                "capacity_overdue_exceeded": 35,
            },
            "bonuses": {
                "completed_last_30d_cap": 15,
                "role_match": 10,
                "preferred_review_type": 10,
                "preferred_target_coverage_level": 10,
            },
            "bounded_range": [0, 100],
        }

    def generate_assignment_suggestions(
        self,
        *,
        organization_id: uuid.UUID,
        framework_id: uuid.UUID,
        review_id: uuid.UUID,
        persist: bool,
        limit: int,
        actor_user_id: uuid.UUID,
        proposed_policy_override: FrameworkReviewerCapacityPolicy | None = None,
    ) -> tuple[FrameworkPackReviewRun, list[FrameworkReviewAssignmentSuggestion], list[dict[str, Any]]]:
        review = self.review_service.require_review(
            organization_id=organization_id,
            framework_id=framework_id,
            review_id=review_id,
        )

        now = self.now()
        reviewers = self._eligible_reviewers(organization_id=organization_id)
        active_policies = self._active_policies(organization_id=organization_id)
        user_ids = [item["user_id"] for item in reviewers]
        stats = self._assignment_stats(organization_id=organization_id, user_ids=user_ids, now=now)

        existing_open_assignments = self.db.execute(
            select(FrameworkPackReviewAssignment.assigned_to_user_id).where(
                FrameworkPackReviewAssignment.organization_id == organization_id,
                FrameworkPackReviewAssignment.review_run_id == review_id,
                FrameworkPackReviewAssignment.status.in_(_OPEN_ASSIGNMENT_STATUSES),
            )
        ).scalars().all()
        excluded_user_ids = set(existing_open_assignments)

        candidate_entries: list[dict[str, Any]] = []
        for reviewer in reviewers:
            if reviewer["user_id"] in excluded_user_ids:
                continue
            reviewer_stats = stats.get(
                reviewer["user_id"],
                {
                    "active_assignments": 0,
                    "accepted_assignments": 0,
                    "overdue_assignments": 0,
                    "completed_assignments_last_30d": 0,
                    "open_escalations": 0,
                },
            )
            policy = self._matching_policy_with_override(
                role_name=reviewer["role_name"],
                active_policies=active_policies,
                proposed_policy_override=proposed_policy_override,
            )
            score, rationale, scoring_json = self._score_reviewer(
                review=review,
                reviewer=reviewer,
                reviewer_stats=reviewer_stats,
                policy=policy,
            )
            candidate_entries.append(
                {
                    "organization_id": organization_id,
                    "review_run_id": review_id,
                    "suggested_user_id": reviewer["user_id"],
                    "score": score,
                    "status": "open",
                    "rationale": rationale,
                    "scoring_json": scoring_json,
                    "generated_by_user_id": actor_user_id,
                    "generated_at": now,
                    "role_name": reviewer["role_name"],
                    "active_assignments": reviewer_stats["active_assignments"],
                    "overdue_assignments": reviewer_stats["overdue_assignments"],
                }
            )

        candidate_entries.sort(
            key=lambda item: (
                -item["score"],
                item["overdue_assignments"],
                item["active_assignments"],
                str(item["suggested_user_id"]),
            )
        )
        ranked = candidate_entries[:limit]
        for idx, entry in enumerate(ranked, start=1):
            entry["rank"] = idx

        persisted_rows: list[FrameworkReviewAssignmentSuggestion] = []
        if persist:
            existing_suggestions = self.repo.list_assignment_suggestions_for_review(
                organization_id=organization_id,
                review_run_id=review_id,
            )
            for row in existing_suggestions:
                if row.status == "open":
                    row.status = "superseded"

            for entry in ranked:
                row = FrameworkReviewAssignmentSuggestion(
                    organization_id=organization_id,
                    review_run_id=review_id,
                    suggested_user_id=entry["suggested_user_id"],
                    score=entry["score"],
                    rank=entry["rank"],
                    status="open",
                    rationale=entry["rationale"],
                    scoring_json=entry["scoring_json"],
                    generated_by_user_id=actor_user_id,
                    generated_at=now,
                )
                self.db.add(row)
                persisted_rows.append(row)
            self.db.flush()

        return review, persisted_rows, ranked

    def simulate_capacity_policy(
        self,
        *,
        organization_id: uuid.UUID,
        role_name: str | None,
        max_active_assignments: int,
        max_overdue_assignments: int,
        preferred_review_types_json: list[str] | None,
        preferred_target_coverage_levels_json: list[str] | None,
        review_type: str | None,
        target_coverage_level: str | None,
    ) -> dict[str, Any]:
        now = self.now()
        reviewers = self._eligible_reviewers(organization_id=organization_id)
        active_policies = self._active_policies(organization_id=organization_id)
        user_ids = [item["user_id"] for item in reviewers]
        stats = self._assignment_stats(organization_id=organization_id, user_ids=user_ids, now=now)
        proposed_policy = self._build_proposed_policy(
            organization_id=organization_id,
            role_name=role_name,
            max_active_assignments=max_active_assignments,
            max_overdue_assignments=max_overdue_assignments,
            preferred_review_types_json=preferred_review_types_json,
            preferred_target_coverage_levels_json=preferred_target_coverage_levels_json,
            now=now,
        )

        pseudo_review = FrameworkPackReviewRun(
            organization_id=organization_id,
            framework_id=uuid.UUID(int=0),
            review_type=review_type or "simulation_review",
            target_coverage_level=target_coverage_level or "simulation_level",
            status="running",
            started_at=now,
            checklist_json={},
            coverage_snapshot_json={},
            caveat=SIMULATION_CAVEAT,
        )

        comparisons: list[dict[str, Any]] = []
        current_scores: list[int] = []
        simulated_scores: list[int] = []
        current_overloaded = 0
        simulated_overloaded = 0
        reviewers_with_overdue = 0

        for reviewer in reviewers:
            user_id = reviewer["user_id"]
            role = reviewer["role_name"]
            reviewer_stats = stats.get(
                user_id,
                {
                    "active_assignments": 0,
                    "accepted_assignments": 0,
                    "overdue_assignments": 0,
                    "completed_assignments_last_30d": 0,
                    "open_escalations": 0,
                },
            )
            current_policy = self._matching_policy(role_name=role, active_policies=active_policies)
            simulated_policy = self._matching_policy_with_override(
                role_name=role,
                active_policies=active_policies,
                proposed_policy_override=proposed_policy,
            )

            current_score, _, current_scoring_json = self._score_reviewer(
                review=pseudo_review,
                reviewer=reviewer,
                reviewer_stats=reviewer_stats,
                policy=current_policy,
            )
            simulated_score, _, simulated_scoring_json = self._score_reviewer(
                review=pseudo_review,
                reviewer=reviewer,
                reviewer_stats=reviewer_stats,
                policy=simulated_policy,
            )
            current_capacity_remaining = self._capacity_remaining(
                policy=current_policy,
                active_assignments=reviewer_stats["active_assignments"],
                overdue_assignments=reviewer_stats["overdue_assignments"],
            )
            simulated_capacity_remaining = self._capacity_remaining(
                policy=simulated_policy,
                active_assignments=reviewer_stats["active_assignments"],
                overdue_assignments=reviewer_stats["overdue_assignments"],
            )

            delta = simulated_score - current_score
            reason = "no score change"
            if delta > 0:
                reason = "higher score from proposed policy preference/capacity profile"
            elif delta < 0:
                reason = "lower score from proposed policy preference/capacity profile"

            current_scores.append(current_score)
            simulated_scores.append(simulated_score)
            if current_capacity_remaining is not None and current_capacity_remaining <= 0:
                current_overloaded += 1
            if simulated_capacity_remaining is not None and simulated_capacity_remaining <= 0:
                simulated_overloaded += 1
            if reviewer_stats["overdue_assignments"] > 0:
                reviewers_with_overdue += 1

            comparisons.append(
                {
                    "user_id": user_id,
                    "role_name": role,
                    "current_workload_score": current_score,
                    "simulated_workload_score": simulated_score,
                    "delta": delta,
                    "reason": reason,
                    "current_capacity_remaining": current_capacity_remaining,
                    "simulated_capacity_remaining": simulated_capacity_remaining,
                    "active_assignments": reviewer_stats["active_assignments"],
                    "overdue_assignments": reviewer_stats["overdue_assignments"],
                    "open_escalations": reviewer_stats["open_escalations"],
                    "current_scoring_json": current_scoring_json,
                    "simulated_scoring_json": simulated_scoring_json,
                    "provenance": SIMULATION_PROVENANCE,
                }
            )

        total_open_assignments = int(
            self.db.execute(
                select(func.count(FrameworkPackReviewAssignment.id)).where(
                    FrameworkPackReviewAssignment.organization_id == organization_id,
                    FrameworkPackReviewAssignment.status.in_(_OPEN_ASSIGNMENT_STATUSES),
                )
            ).scalar_one()
        )
        total_open_escalations = int(
            self.db.execute(
                select(func.count(FrameworkReviewEscalationEvent.id)).where(
                    FrameworkReviewEscalationEvent.organization_id == organization_id,
                    FrameworkReviewEscalationEvent.status == "open",
                )
            ).scalar_one()
        )
        active_reviewers = len(reviewers)

        return {
            "current_summary": {
                "active_reviewers": active_reviewers,
                "overloaded_reviewers": current_overloaded,
                "reviewers_with_overdue_assignments": reviewers_with_overdue,
                "total_open_assignments": total_open_assignments,
                "total_open_escalations": total_open_escalations,
                "average_workload_score": round(sum(current_scores) / active_reviewers, 2) if active_reviewers else 0.0,
            },
            "simulated_summary": {
                "active_reviewers": active_reviewers,
                "overloaded_reviewers": simulated_overloaded,
                "reviewers_with_overdue_assignments": reviewers_with_overdue,
                "total_open_assignments": total_open_assignments,
                "total_open_escalations": total_open_escalations,
                "average_workload_score": round(sum(simulated_scores) / active_reviewers, 2) if active_reviewers else 0.0,
            },
            "reviewer_comparisons": comparisons,
            "scoring_formula": self.scoring_formula(),
            "provenance": SIMULATION_PROVENANCE,
            "caveat": SIMULATION_CAVEAT,
        }

    def simulate_assignment_suggestions(
        self,
        *,
        organization_id: uuid.UUID,
        framework_id: uuid.UUID,
        review_id: uuid.UUID,
        limit: int,
        actor_user_id: uuid.UUID,
        proposed_policy_json: dict[str, Any] | None,
    ) -> tuple[FrameworkPackReviewRun, list[dict[str, Any]], dict[str, Any] | None]:
        proposed_policy_override: FrameworkReviewerCapacityPolicy | None = None
        normalized_policy: dict[str, Any] | None = None
        if proposed_policy_json is not None:
            now = self.now()
            max_active_assignments = int(proposed_policy_json.get("max_active_assignments", -1))
            max_overdue_assignments = int(proposed_policy_json.get("max_overdue_assignments", -1))
            proposed_policy_override = self._build_proposed_policy(
                organization_id=organization_id,
                role_name=proposed_policy_json.get("role_name"),
                max_active_assignments=max_active_assignments,
                max_overdue_assignments=max_overdue_assignments,
                preferred_review_types_json=proposed_policy_json.get("preferred_review_types_json"),
                preferred_target_coverage_levels_json=proposed_policy_json.get("preferred_target_coverage_levels_json"),
                now=now,
            )
            normalized_policy = {
                "role_name": proposed_policy_override.role_name,
                "max_active_assignments": proposed_policy_override.max_active_assignments,
                "max_overdue_assignments": proposed_policy_override.max_overdue_assignments,
                "preferred_review_types_json": proposed_policy_override.preferred_review_types_json,
                "preferred_target_coverage_levels_json": proposed_policy_override.preferred_target_coverage_levels_json,
            }

        review, _, ranked = self.generate_assignment_suggestions(
            organization_id=organization_id,
            framework_id=framework_id,
            review_id=review_id,
            persist=False,
            limit=limit,
            actor_user_id=actor_user_id,
            proposed_policy_override=proposed_policy_override,
        )
        for entry in ranked:
            entry["provenance"] = SIMULATION_PROVENANCE
        return review, ranked, normalized_policy

    def _review_selector_for_wave_simulation(
        self,
        *,
        organization_id: uuid.UUID,
        framework_id: uuid.UUID | None,
        review_ids: list[uuid.UUID] | None,
        review_type: str | None,
        target_coverage_level: str | None,
    ) -> list[FrameworkPackReviewRun]:
        if review_ids:
            rows = self.db.execute(
                select(FrameworkPackReviewRun).where(
                    FrameworkPackReviewRun.organization_id == organization_id,
                    FrameworkPackReviewRun.id.in_(review_ids),
                )
            ).scalars().all()
            found_ids = {row.id for row in rows}
            missing = [str(review_id) for review_id in review_ids if review_id not in found_ids]
            if missing:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Framework pack review not found for ids: {', '.join(missing)}",
                )
            filtered = [row for row in rows if row.status in {"running", "completed"}]
            if framework_id is not None:
                filtered = [row for row in filtered if row.framework_id == framework_id]
            if review_type is not None:
                filtered = [row for row in filtered if row.review_type == review_type]
            if target_coverage_level is not None:
                filtered = [row for row in filtered if row.target_coverage_level == target_coverage_level]
            return sorted(
                filtered,
                key=lambda row: (
                    self._ensure_utc(row.started_at),
                    str(row.id),
                ),
            )

        query = select(FrameworkPackReviewRun).where(
            FrameworkPackReviewRun.organization_id == organization_id,
            FrameworkPackReviewRun.status.in_(["running", "completed"]),
        )
        if framework_id is not None:
            query = query.where(FrameworkPackReviewRun.framework_id == framework_id)
        if review_type is not None:
            query = query.where(FrameworkPackReviewRun.review_type == review_type)
        if target_coverage_level is not None:
            query = query.where(FrameworkPackReviewRun.target_coverage_level == target_coverage_level)
        return self.db.execute(
            query.order_by(FrameworkPackReviewRun.started_at.asc(), FrameworkPackReviewRun.id.asc())
        ).scalars().all()

    def simulate_review_waves(
        self,
        *,
        organization_id: uuid.UUID,
        framework_id: uuid.UUID | None,
        review_ids: list[uuid.UUID] | None,
        review_type: str | None,
        target_coverage_level: str | None,
        max_waves: int,
        max_reviews_per_wave: int,
        proposed_policy_json: dict[str, Any] | None,
        limit_reviewers: list[uuid.UUID] | None,
        include_existing_assignments: bool,
    ) -> dict[str, Any]:
        now = self.now()
        reviews = self._review_selector_for_wave_simulation(
            organization_id=organization_id,
            framework_id=framework_id,
            review_ids=review_ids,
            review_type=review_type,
            target_coverage_level=target_coverage_level,
        )
        selected_reviews_count = len(reviews)
        if selected_reviews_count == 0:
            return {
                "simulation_id": str(uuid.uuid4()),
                "selected_reviews_count": 0,
                "waves": [],
                "unassigned_reviews": [],
                "reviewer_load_projection": [],
                "scoring_formula": self.scoring_formula(),
                "constraints_applied": {
                    "framework_id": str(framework_id) if framework_id else None,
                    "review_ids_supplied": len(review_ids or []),
                    "review_type": review_type,
                    "target_coverage_level": target_coverage_level,
                    "max_waves": max_waves,
                    "max_reviews_per_wave": max_reviews_per_wave,
                    "limit_reviewers": [str(item) for item in (limit_reviewers or [])],
                    "include_existing_assignments": include_existing_assignments,
                },
                "provenance": SIMULATION_PROVENANCE,
                "caveat": WAVE_SIMULATION_CAVEAT,
            }

        active_policies = self._active_policies(organization_id=organization_id)
        proposed_policy_override: FrameworkReviewerCapacityPolicy | None = None
        proposed_policy_used: dict[str, Any] | None = None
        if proposed_policy_json is not None:
            proposed_policy_override = self._build_proposed_policy(
                organization_id=organization_id,
                role_name=proposed_policy_json.get("role_name"),
                max_active_assignments=int(proposed_policy_json.get("max_active_assignments", -1)),
                max_overdue_assignments=int(proposed_policy_json.get("max_overdue_assignments", -1)),
                preferred_review_types_json=proposed_policy_json.get("preferred_review_types_json"),
                preferred_target_coverage_levels_json=proposed_policy_json.get("preferred_target_coverage_levels_json"),
                now=now,
            )
            proposed_policy_used = {
                "role_name": proposed_policy_override.role_name,
                "max_active_assignments": proposed_policy_override.max_active_assignments,
                "max_overdue_assignments": proposed_policy_override.max_overdue_assignments,
                "preferred_review_types_json": proposed_policy_override.preferred_review_types_json,
                "preferred_target_coverage_levels_json": proposed_policy_override.preferred_target_coverage_levels_json,
            }

        reviewers = self._eligible_reviewers(organization_id=organization_id)
        if limit_reviewers:
            allowed = set(limit_reviewers)
            reviewers = [item for item in reviewers if item["user_id"] in allowed]

        reviewer_ids = [item["user_id"] for item in reviewers]
        stats = self._assignment_stats(organization_id=organization_id, user_ids=reviewer_ids, now=now)
        if not include_existing_assignments:
            for user_id in reviewer_ids:
                current = stats.get(user_id)
                if current is None:
                    continue
                current["active_assignments"] = 0
                current["accepted_assignments"] = 0
                current["overdue_assignments"] = 0
                current["open_escalations"] = 0

        projected_stats = {
            user_id: {
                "active_assignments": int(values.get("active_assignments", 0)),
                "accepted_assignments": int(values.get("accepted_assignments", 0)),
                "overdue_assignments": int(values.get("overdue_assignments", 0)),
                "completed_assignments_last_30d": int(values.get("completed_assignments_last_30d", 0)),
                "open_escalations": int(values.get("open_escalations", 0)),
            }
            for user_id, values in stats.items()
        }

        open_assignment_users_by_review: dict[uuid.UUID, set[uuid.UUID]] = {}
        if include_existing_assignments:
            open_assignment_rows = self.db.execute(
                select(FrameworkPackReviewAssignment.review_run_id, FrameworkPackReviewAssignment.assigned_to_user_id).where(
                    FrameworkPackReviewAssignment.organization_id == organization_id,
                    FrameworkPackReviewAssignment.review_run_id.in_([row.id for row in reviews]),
                    FrameworkPackReviewAssignment.status.in_(_OPEN_ASSIGNMENT_STATUSES),
                )
            ).all()
            for review_run_id, assigned_user_id in open_assignment_rows:
                if review_run_id not in open_assignment_users_by_review:
                    open_assignment_users_by_review[review_run_id] = set()
                open_assignment_users_by_review[review_run_id].add(assigned_user_id)

        waves: list[dict[str, Any]] = []
        unassigned_reviews: list[dict[str, Any]] = []
        queue: list[FrameworkPackReviewRun] = list(reviews)
        wave_number = 0

        while queue and wave_number < max_waves:
            wave_number += 1
            review_batch = queue[:max_reviews_per_wave]
            queue = queue[max_reviews_per_wave:]

            planned_reviews: list[dict[str, Any]] = []
            wave_unassigned: list[dict[str, Any]] = []

            for review in review_batch:
                existing_assignees = open_assignment_users_by_review.get(review.id, set())
                if existing_assignees:
                    unassigned = {
                        "review_id": review.id,
                        "reason": "review already has open assignment(s)",
                        "candidate_count": 0,
                        "constraints_failed": ["existing_open_assignment"],
                    }
                    wave_unassigned.append(unassigned)
                    unassigned_reviews.append(unassigned)
                    continue

                candidates: list[dict[str, Any]] = []
                excluded_by_constraints = {
                    "capacity_active_full": 0,
                    "capacity_overdue_exceeded": 0,
                    "limit_reviewers_no_candidates": 0,
                }
                for reviewer in reviewers:
                    reviewer_stats = projected_stats.get(
                        reviewer["user_id"],
                        {
                            "active_assignments": 0,
                            "accepted_assignments": 0,
                            "overdue_assignments": 0,
                            "completed_assignments_last_30d": 0,
                            "open_escalations": 0,
                        },
                    )
                    policy = self._matching_policy_with_override(
                        role_name=reviewer["role_name"],
                        active_policies=active_policies,
                        proposed_policy_override=proposed_policy_override,
                    )
                    if policy is not None and reviewer_stats["active_assignments"] >= policy.max_active_assignments:
                        excluded_by_constraints["capacity_active_full"] += 1
                        continue
                    if policy is not None and reviewer_stats["overdue_assignments"] > policy.max_overdue_assignments:
                        excluded_by_constraints["capacity_overdue_exceeded"] += 1
                        continue
                    score, rationale, scoring_json = self._score_reviewer(
                        review=review,
                        reviewer=reviewer,
                        reviewer_stats=reviewer_stats,
                        policy=policy,
                    )
                    candidates.append(
                        {
                            "review_id": review.id,
                            "framework_id": review.framework_id,
                            "review_type": review.review_type,
                            "target_coverage_level": review.target_coverage_level,
                            "suggested_reviewer_id": reviewer["user_id"],
                            "score": score,
                            "rationale": rationale,
                            "scoring_json": scoring_json,
                            "active_assignments": reviewer_stats["active_assignments"],
                            "overdue_assignments": reviewer_stats["overdue_assignments"],
                        }
                    )

                candidates.sort(
                    key=lambda item: (
                        -item["score"],
                        item["overdue_assignments"],
                        item["active_assignments"],
                        str(item["suggested_reviewer_id"]),
                    )
                )

                if not candidates:
                    constraints_failed = [
                        key for key, value in excluded_by_constraints.items() if value > 0 and key != "limit_reviewers_no_candidates"
                    ]
                    if limit_reviewers and not constraints_failed:
                        constraints_failed.append("limit_reviewers_no_candidates")
                    unassigned = {
                        "review_id": review.id,
                        "reason": "no eligible reviewers after deterministic capacity constraints",
                        "candidate_count": 0,
                        "constraints_failed": constraints_failed,
                    }
                    wave_unassigned.append(unassigned)
                    unassigned_reviews.append(unassigned)
                    continue

                for idx, entry in enumerate(candidates, start=1):
                    entry["rank"] = idx
                selected = candidates[0]
                selected_user_id = selected["suggested_reviewer_id"]
                projected_stats[selected_user_id]["active_assignments"] += 1

                planned_reviews.append(
                    {
                        "review_id": selected["review_id"],
                        "framework_id": selected["framework_id"],
                        "review_type": selected["review_type"],
                        "target_coverage_level": selected["target_coverage_level"],
                        "suggested_reviewer_id": selected_user_id,
                        "score": selected["score"],
                        "rank": selected["rank"],
                        "rationale": selected["rationale"],
                        "scoring_json": selected["scoring_json"],
                    }
                )

            reviewer_projection_after_wave: list[dict[str, Any]] = []
            for reviewer in reviewers:
                reviewer_stats = projected_stats.get(reviewer["user_id"], {})
                policy = self._matching_policy_with_override(
                    role_name=reviewer["role_name"],
                    active_policies=active_policies,
                    proposed_policy_override=proposed_policy_override,
                )
                reviewer_projection_after_wave.append(
                    {
                        "user_id": reviewer["user_id"],
                        "role_name": reviewer["role_name"],
                        "active_assignments": int(reviewer_stats.get("active_assignments", 0)),
                        "overdue_assignments": int(reviewer_stats.get("overdue_assignments", 0)),
                        "open_escalations": int(reviewer_stats.get("open_escalations", 0)),
                        "completed_assignments_last_30d": int(reviewer_stats.get("completed_assignments_last_30d", 0)),
                        "workload_score": self._workload_score(
                            active=int(reviewer_stats.get("active_assignments", 0)),
                            overdue=int(reviewer_stats.get("overdue_assignments", 0)),
                            escalations=int(reviewer_stats.get("open_escalations", 0)),
                            completed_last_30d=int(reviewer_stats.get("completed_assignments_last_30d", 0)),
                        ),
                        "capacity_remaining": self._capacity_remaining(
                            policy=policy,
                            active_assignments=int(reviewer_stats.get("active_assignments", 0)),
                            overdue_assignments=int(reviewer_stats.get("overdue_assignments", 0)),
                        ),
                        "provenance": SIMULATION_PROVENANCE,
                    }
                )
            reviewer_projection_after_wave.sort(key=lambda item: (item["role_name"], str(item["user_id"])))

            waves.append(
                {
                    "wave_number": wave_number,
                    "planned_reviews": planned_reviews,
                    "reviewer_projection_after_wave": reviewer_projection_after_wave,
                    "unassigned_in_wave": wave_unassigned,
                    "rationale": (
                        f"Wave {wave_number} planned {len(planned_reviews)} review(s); "
                        f"{len(wave_unassigned)} unassigned after deterministic capacity filtering."
                    ),
                }
            )

        final_projection = waves[-1]["reviewer_projection_after_wave"] if waves else []
        return {
            "simulation_id": str(uuid.uuid4()),
            "selected_reviews_count": selected_reviews_count,
            "waves": waves,
            "unassigned_reviews": unassigned_reviews,
            "reviewer_load_projection": final_projection,
            "scoring_formula": self.scoring_formula(),
            "constraints_applied": {
                "framework_id": str(framework_id) if framework_id else None,
                "review_ids_supplied": len(review_ids or []),
                "review_type": review_type,
                "target_coverage_level": target_coverage_level,
                "max_waves": max_waves,
                "max_reviews_per_wave": max_reviews_per_wave,
                "limit_reviewers": [str(item) for item in (limit_reviewers or [])],
                "include_existing_assignments": include_existing_assignments,
                "proposed_policy_used": proposed_policy_used,
            },
            "provenance": SIMULATION_PROVENANCE,
            "caveat": WAVE_SIMULATION_CAVEAT,
        }

    def _normalize_batch_plan(
        self,
        *,
        organization_id: uuid.UUID,
        assignments: list[dict[str, Any]] | None,
        wave_simulation_payload: dict[str, Any] | None,
    ) -> tuple[list[dict[str, Any]], list[str], str]:
        if assignments is None and wave_simulation_payload is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="assignments or wave_simulation_payload is required")
        if assignments is not None and wave_simulation_payload is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provide assignments or wave_simulation_payload, not both",
            )

        warnings: list[str] = []
        normalized: list[dict[str, Any]] = []
        source_type = "assignments"
        if assignments is not None:
            for item in assignments:
                due_at = item.get("due_at")
                normalized.append(
                    {
                        "review_run_id": item["review_run_id"],
                        "assigned_to_user_id": item["assigned_to_user_id"],
                        "due_at": self._ensure_utc(due_at) if due_at else None,
                        "notes": item.get("notes"),
                        "rationale": item.get("rationale"),
                        "scoring_json": item.get("scoring_json"),
                    }
                )
        else:
            source_type = "wave_simulation_payload"
            simulation = self.simulate_review_waves(
                organization_id=organization_id,
                framework_id=wave_simulation_payload.get("framework_id"),
                review_ids=wave_simulation_payload.get("review_ids"),
                review_type=wave_simulation_payload.get("review_type"),
                target_coverage_level=wave_simulation_payload.get("target_coverage_level"),
                max_waves=int(wave_simulation_payload.get("max_waves", 3)),
                max_reviews_per_wave=int(wave_simulation_payload.get("max_reviews_per_wave", 10)),
                proposed_policy_json=wave_simulation_payload.get("proposed_policy_json"),
                limit_reviewers=wave_simulation_payload.get("limit_reviewers"),
                include_existing_assignments=bool(wave_simulation_payload.get("include_existing_assignments", True)),
            )
            for wave in simulation["waves"]:
                for planned in wave["planned_reviews"]:
                    normalized.append(
                        {
                            "review_run_id": planned["review_id"],
                            "assigned_to_user_id": planned["suggested_reviewer_id"],
                            "due_at": None,
                            "notes": None,
                            "rationale": planned.get("rationale"),
                            "scoring_json": planned.get("scoring_json"),
                        }
                    )
            unassigned_count = len(simulation.get("unassigned_reviews", []))
            if unassigned_count > 0:
                warnings.append(
                    f"Wave simulation produced {unassigned_count} unassigned review(s); only planned reviews are included."
                )
        normalized.sort(
            key=lambda item: (
                str(item["review_run_id"]),
                str(item["assigned_to_user_id"]),
                item["due_at"].isoformat() if item.get("due_at") else "",
            )
        )
        return normalized, warnings, source_type

    def _plan_hash(
        self,
        *,
        organization_id: uuid.UUID,
        normalized_plan: list[dict[str, Any]],
        notify_assignees: bool,
    ) -> str:
        canonical_items = [
            {
                "review_run_id": str(item["review_run_id"]),
                "assigned_to_user_id": str(item["assigned_to_user_id"]),
                "due_at": item["due_at"].isoformat() if item.get("due_at") else None,
                "notes": item.get("notes"),
            }
            for item in normalized_plan
        ]
        payload = {
            "organization_id": str(organization_id),
            "notify_assignees": bool(notify_assignees),
            "assignments": canonical_items,
        }
        return hashlib.sha256(self._canonical_json(payload).encode("utf-8")).hexdigest()

    def validate_batch_assignment_plan(
        self,
        *,
        organization_id: uuid.UUID,
        assignments: list[dict[str, Any]] | None,
        wave_simulation_payload: dict[str, Any] | None,
        notify_assignees: bool,
    ) -> dict[str, Any]:
        now = self.now()
        normalized_plan, warnings, source_type = self._normalize_batch_plan(
            organization_id=organization_id,
            assignments=assignments,
            wave_simulation_payload=wave_simulation_payload,
        )
        plan_hash = self._plan_hash(
            organization_id=organization_id,
            normalized_plan=normalized_plan,
            notify_assignees=notify_assignees,
        )

        review_ids = [item["review_run_id"] for item in normalized_plan]
        reviews = self.db.execute(
            select(FrameworkPackReviewRun).where(
                FrameworkPackReviewRun.organization_id == organization_id,
                FrameworkPackReviewRun.id.in_(review_ids),
            )
        ).scalars().all()
        review_map = {row.id: row for row in reviews}

        reviewers = self._eligible_reviewers(organization_id=organization_id)
        reviewer_map = {row["user_id"]: row for row in reviewers}
        reviewer_ids = list(reviewer_map.keys())
        stats = self._assignment_stats(organization_id=organization_id, user_ids=reviewer_ids, now=now)
        projected_stats = {
            user_id: {
                "active_assignments": int(values.get("active_assignments", 0)),
                "accepted_assignments": int(values.get("accepted_assignments", 0)),
                "overdue_assignments": int(values.get("overdue_assignments", 0)),
                "completed_assignments_last_30d": int(values.get("completed_assignments_last_30d", 0)),
                "open_escalations": int(values.get("open_escalations", 0)),
            }
            for user_id, values in stats.items()
        }
        active_policies = self._active_policies(organization_id=organization_id)
        if not active_policies:
            warnings.append("No active reviewer capacity policies found; capacity constraints are policy-agnostic.")

        open_rows = self.db.execute(
            select(FrameworkPackReviewAssignment.review_run_id, FrameworkPackReviewAssignment.assigned_to_user_id).where(
                FrameworkPackReviewAssignment.organization_id == organization_id,
                FrameworkPackReviewAssignment.review_run_id.in_(review_ids),
                FrameworkPackReviewAssignment.status.in_(_OPEN_ASSIGNMENT_STATUSES),
            )
        ).all()
        existing_open_pairs = {(row[0], row[1]) for row in open_rows}

        review_counts: dict[uuid.UUID, int] = {}
        for item in normalized_plan:
            review_id = item["review_run_id"]
            review_counts[review_id] = review_counts.get(review_id, 0) + 1
        duplicate_review_ids = {review_id for review_id, count in review_counts.items() if count > 1}

        validation_items: list[dict[str, Any]] = []
        valid_items = 0
        for item in normalized_plan:
            reasons: list[str] = []
            review_id = item["review_run_id"]
            assignee_id = item["assigned_to_user_id"]
            review = review_map.get(review_id)
            if review is None:
                reasons.append("review_not_found_or_cross_tenant")
            if review_id in duplicate_review_ids:
                reasons.append("duplicate_review_in_request")

            reviewer = reviewer_map.get(assignee_id)
            if reviewer is None:
                reasons.append("assignee_not_active_org_member_or_not_eligible_for_review")

            if (review_id, assignee_id) in existing_open_pairs:
                reasons.append("existing_open_assignment_for_same_assignee")

            if reviewer is not None:
                user_stats = projected_stats.get(
                    assignee_id,
                    {
                        "active_assignments": 0,
                        "accepted_assignments": 0,
                        "overdue_assignments": 0,
                        "completed_assignments_last_30d": 0,
                        "open_escalations": 0,
                    },
                )
                policy = self._matching_policy(
                    role_name=str(reviewer["role_name"]),
                    active_policies=active_policies,
                )
                if policy is not None and user_stats["active_assignments"] >= policy.max_active_assignments:
                    reasons.append("capacity_active_full")
                if policy is not None and user_stats["overdue_assignments"] > policy.max_overdue_assignments:
                    reasons.append("capacity_overdue_exceeded")
                if not reasons:
                    projected_stats[assignee_id]["active_assignments"] = user_stats["active_assignments"] + 1

            is_valid = len(reasons) == 0
            if is_valid:
                valid_items += 1
            validation_items.append(
                {
                    "review_run_id": str(review_id),
                    "assigned_to_user_id": str(assignee_id),
                    "due_at": item["due_at"].isoformat() if item.get("due_at") else None,
                    "notes": item.get("notes"),
                    "valid": is_valid,
                    "reasons": reasons,
                    "rationale": item.get("rationale"),
                    "scoring_json": item.get("scoring_json"),
                }
            )

        invalid_items = len(validation_items) - valid_items
        report = {
            "source_type": source_type,
            "items": validation_items,
            "total_items": len(validation_items),
            "valid_items": valid_items,
            "invalid_items": invalid_items,
            "warnings": warnings,
        }
        return {
            "valid": invalid_items == 0,
            "plan_hash": plan_hash,
            "required_confirmation_text": BATCH_ASSIGNMENT_CONFIRMATION_TEXT,
            "total_items": len(validation_items),
            "valid_items": valid_items,
            "invalid_items": invalid_items,
            "warnings": warnings,
            "validation_report": report,
            "caveat": BATCH_ASSIGNMENT_CAVEAT,
            "normalized_plan": normalized_plan,
            "review_map": review_map,
        }

    def apply_batch_assignment_plan(
        self,
        *,
        organization_id: uuid.UUID,
        requested_by_user_id: uuid.UUID,
        applied_by_user_id: uuid.UUID,
        provided_plan_hash: str,
        confirmation_text: str,
        assignments: list[dict[str, Any]] | None,
        wave_simulation_payload: dict[str, Any] | None,
        notify_assignees: bool,
    ) -> tuple[FrameworkReviewBatchAssignmentRun, list[FrameworkReviewBatchAssignmentItem], dict[str, Any]]:
        if confirmation_text != BATCH_ASSIGNMENT_CONFIRMATION_TEXT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="confirmation_text must exactly equal CONFIRM_BATCH_ASSIGNMENTS",
            )
        validation = self.validate_batch_assignment_plan(
            organization_id=organization_id,
            assignments=assignments,
            wave_simulation_payload=wave_simulation_payload,
            notify_assignees=notify_assignees,
        )
        if validation["plan_hash"] != provided_plan_hash:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="plan_hash mismatch")

        run = FrameworkReviewBatchAssignmentRun(
            organization_id=organization_id,
            status="validated",
            plan_hash=validation["plan_hash"],
            confirmation_text=confirmation_text,
            requested_by_user_id=requested_by_user_id,
            cancellation_requires_approval=self._organization_batch_cancellation_requires_approval(
                organization_id=organization_id
            ),
            notify_assignees=notify_assignees,
            total_items=validation["total_items"],
            validation_report_json=validation["validation_report"],
        )
        self.db.add(run)
        self.db.flush()

        item_rows: list[FrameworkReviewBatchAssignmentItem] = []
        created_assignments_count = 0
        skipped_items_count = 0
        failed_items_count = 0
        item_results: list[dict[str, Any]] = []

        open_rows = self.db.execute(
            select(FrameworkPackReviewAssignment.review_run_id, FrameworkPackReviewAssignment.assigned_to_user_id).where(
                FrameworkPackReviewAssignment.organization_id == organization_id,
                FrameworkPackReviewAssignment.status.in_(_OPEN_ASSIGNMENT_STATUSES),
            )
        ).all()
        open_pairs = {(row[0], row[1]) for row in open_rows}

        for item in validation["validation_report"]["items"]:
            row = FrameworkReviewBatchAssignmentItem(
                organization_id=organization_id,
                batch_run_id=run.id,
                review_run_id=uuid.UUID(item["review_run_id"]),
                assigned_to_user_id=uuid.UUID(item["assigned_to_user_id"]),
                status="pending",
                scoring_json=item.get("scoring_json"),
                rationale=item.get("rationale"),
                created_at=self.now(),
            )
            self.db.add(row)
            self.db.flush()

            pair = (row.review_run_id, row.assigned_to_user_id)
            if not item["valid"]:
                row.status = "skipped_invalid"
                row.skipped_reason = ", ".join(item.get("reasons") or ["invalid"])
                skipped_items_count += 1
            elif pair in open_pairs:
                row.status = "skipped_duplicate"
                row.skipped_reason = "existing_open_assignment_for_same_assignee"
                skipped_items_count += 1
            else:
                review = validation["review_map"].get(row.review_run_id)
                if review is None:
                    row.status = "skipped_invalid"
                    row.skipped_reason = "review_not_found_or_cross_tenant"
                    skipped_items_count += 1
                else:
                    try:
                        assignment, queued_email_id = self.review_service.create_assignment(
                            organization_id=organization_id,
                            framework_id=review.framework_id,
                            review_id=review.id,
                            assigned_to_user_id=row.assigned_to_user_id,
                            assigned_by_user_id=applied_by_user_id,
                            due_at=self._ensure_utc(datetime.fromisoformat(item["due_at"])) if item.get("due_at") else None,
                            notes=item.get("notes"),
                            notify=notify_assignees,
                        )
                        row.status = "created"
                        row.created_assignment_id = assignment.id
                        created_assignments_count += 1
                        open_pairs.add(pair)
                        item_results.append(
                            {
                                "batch_item_id": str(row.id),
                                "status": row.status,
                                "review_run_id": str(row.review_run_id),
                                "assigned_to_user_id": str(row.assigned_to_user_id),
                                "created_assignment_id": str(assignment.id),
                                "queued_email_id": str(queued_email_id) if queued_email_id else None,
                            }
                        )
                    except HTTPException as exc:
                        row.status = "failed"
                        row.error_message = str(exc.detail)
                        failed_items_count += 1
                    except Exception as exc:  # pragma: no cover - defensive catch for transactional safety
                        row.status = "failed"
                        row.error_message = str(exc)
                        failed_items_count += 1

            if row.status != "created":
                item_results.append(
                    {
                        "batch_item_id": str(row.id),
                        "status": row.status,
                        "review_run_id": str(row.review_run_id),
                        "assigned_to_user_id": str(row.assigned_to_user_id),
                        "created_assignment_id": str(row.created_assignment_id) if row.created_assignment_id else None,
                        "skipped_reason": row.skipped_reason,
                        "error_message": row.error_message,
                    }
                )
            item_rows.append(row)

        run.status = "failed" if failed_items_count > 0 else "applied"
        run.applied_by_user_id = applied_by_user_id
        run.applied_at = self.now()
        run.created_assignments_count = created_assignments_count
        run.skipped_items_count = skipped_items_count
        run.failed_items_count = failed_items_count
        run.result_json = {"items": item_results}
        self.db.flush()

        result = {
            "run_id": run.id,
            "status": run.status,
            "plan_hash": run.plan_hash,
            "required_confirmation_text": BATCH_ASSIGNMENT_CONFIRMATION_TEXT,
            "total_items": run.total_items,
            "created_assignments_count": created_assignments_count,
            "skipped_items_count": skipped_items_count,
            "failed_items_count": failed_items_count,
            "notify_assignees": notify_assignees,
            "result": run.result_json or {"items": []},
            "caveat": BATCH_ASSIGNMENT_CAVEAT,
        }
        return run, item_rows, result

    def list_batch_assignment_runs(
        self,
        *,
        organization_id: uuid.UUID,
        status_filter: str | None,
        limit: int,
        offset: int,
    ) -> list[FrameworkReviewBatchAssignmentRun]:
        query = select(FrameworkReviewBatchAssignmentRun).where(
            FrameworkReviewBatchAssignmentRun.organization_id == organization_id
        )
        if status_filter is not None:
            query = query.where(FrameworkReviewBatchAssignmentRun.status == status_filter)
        return self.db.execute(
            query.order_by(FrameworkReviewBatchAssignmentRun.created_at.desc()).offset(offset).limit(limit)
        ).scalars().all()

    def get_batch_assignment_run(
        self,
        *,
        organization_id: uuid.UUID,
        run_id: uuid.UUID,
    ) -> FrameworkReviewBatchAssignmentRun:
        row = self.db.execute(
            select(FrameworkReviewBatchAssignmentRun).where(FrameworkReviewBatchAssignmentRun.id == run_id)
        ).scalar_one_or_none()
        if row is None or row.organization_id != organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework review batch assignment run not found")
        return row

    def list_batch_assignment_items(
        self,
        *,
        organization_id: uuid.UUID,
        run_id: uuid.UUID,
    ) -> list[FrameworkReviewBatchAssignmentItem]:
        return self.db.execute(
            select(FrameworkReviewBatchAssignmentItem)
            .where(
                FrameworkReviewBatchAssignmentItem.organization_id == organization_id,
                FrameworkReviewBatchAssignmentItem.batch_run_id == run_id,
            )
            .order_by(FrameworkReviewBatchAssignmentItem.created_at.asc(), FrameworkReviewBatchAssignmentItem.id.asc())
        ).scalars().all()

    def _batch_run_open_cancellation_request(
        self,
        *,
        organization_id: uuid.UUID,
        run_id: uuid.UUID,
    ) -> FrameworkReviewBatchCancellationRequest | None:
        return self.db.execute(
            select(FrameworkReviewBatchCancellationRequest).where(
                FrameworkReviewBatchCancellationRequest.organization_id == organization_id,
                FrameworkReviewBatchCancellationRequest.batch_run_id == run_id,
                FrameworkReviewBatchCancellationRequest.status.in_(("pending", "approved")),
            )
        ).scalar_one_or_none()

    @staticmethod
    def _run_has_applied_assignments(run: FrameworkReviewBatchAssignmentRun) -> bool:
        return run.status == "applied" and int(run.created_assignments_count or 0) > 0

    @staticmethod
    def _run_cancellation_requires_approval(run: FrameworkReviewBatchAssignmentRun) -> bool:
        return bool(run.cancellation_requires_approval)

    def _organization_batch_cancellation_requires_approval(self, *, organization_id: uuid.UUID) -> bool:
        row = self.db.execute(
            select(OrganizationGovernanceSetting).where(
                OrganizationGovernanceSetting.organization_id == organization_id
            )
        ).scalar_one_or_none()
        if row is None:
            return False
        return bool(row.batch_cancellation_requires_approval)

    def cancel_batch_assignment_run(
        self,
        *,
        organization_id: uuid.UUID,
        run_id: uuid.UUID,
        cancelled_by_user_id: uuid.UUID,
        cancellation_reason: str,
        enforce_approval_gate: bool = True,
    ) -> FrameworkReviewBatchAssignmentRun:
        run = self.get_batch_assignment_run(organization_id=organization_id, run_id=run_id)
        if not cancellation_reason.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cancellation_reason is required")
        if enforce_approval_gate and self._run_cancellation_requires_approval(run):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=BATCH_CANCELLATION_APPROVAL_REQUIRED_DETAIL)
        if run.status == "cancelled":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Batch assignment run is already cancelled")
        if self._run_has_applied_assignments(run):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Applied batch runs cannot be cancelled because assignments were already created. "
                    "Cancel individual assignments instead."
                ),
            )

        previous_status = run.status
        run.status = "cancelled"
        run.cancelled_by_user_id = cancelled_by_user_id
        run.cancelled_at = self.now()
        run.cancellation_reason = cancellation_reason.strip()
        run.cancellation_metadata_json = {
            "cancelled_from_status": previous_status,
            "applied_at": run.applied_at.isoformat() if run.applied_at is not None else None,
            "created_assignments_count": int(run.created_assignments_count or 0),
        }
        self.db.flush()
        return run

    def update_batch_cancellation_requirement(
        self,
        *,
        organization_id: uuid.UUID,
        run_id: uuid.UUID,
        enabled: bool,
    ) -> FrameworkReviewBatchAssignmentRun:
        run = self.get_batch_assignment_run(organization_id=organization_id, run_id=run_id)
        if run.status == "cancelled":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot update cancellation approval requirement for a cancelled batch run",
            )
        run.cancellation_requires_approval = bool(enabled)
        self.db.flush()
        return run

    def create_batch_cancellation_request(
        self,
        *,
        organization_id: uuid.UUID,
        run_id: uuid.UUID,
        requested_by_user_id: uuid.UUID,
        reason: str,
    ) -> FrameworkReviewBatchCancellationRequest:
        run = self.get_batch_assignment_run(organization_id=organization_id, run_id=run_id)
        if not reason.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="reason is required")
        if run.status == "cancelled":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Batch assignment run is already cancelled")
        if self._run_has_applied_assignments(run):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Applied batch runs cannot be cancelled because assignments were already created. "
                    "Cancel individual assignments instead."
                ),
            )
        existing = self._batch_run_open_cancellation_request(organization_id=organization_id, run_id=run_id)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An open cancellation request already exists for this batch run",
            )

        row = FrameworkReviewBatchCancellationRequest(
            organization_id=organization_id,
            batch_run_id=run.id,
            status="pending",
            reason=reason.strip(),
            requested_by_user_id=requested_by_user_id,
            requested_at=self.now(),
        )
        self.db.add(row)
        self.db.flush()
        run.cancellation_request_id = row.id
        self.db.flush()
        return row

    def list_batch_cancellation_requests(
        self,
        *,
        organization_id: uuid.UUID,
        status_filter: str | None,
        batch_run_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> list[FrameworkReviewBatchCancellationRequest]:
        query = select(FrameworkReviewBatchCancellationRequest).where(
            FrameworkReviewBatchCancellationRequest.organization_id == organization_id
        )
        if status_filter is not None:
            query = query.where(FrameworkReviewBatchCancellationRequest.status == status_filter)
        if batch_run_id is not None:
            query = query.where(FrameworkReviewBatchCancellationRequest.batch_run_id == batch_run_id)
        return self.db.execute(
            query.order_by(FrameworkReviewBatchCancellationRequest.created_at.desc()).offset(offset).limit(limit)
        ).scalars().all()

    def get_batch_cancellation_request(
        self,
        *,
        organization_id: uuid.UUID,
        request_id: uuid.UUID,
    ) -> FrameworkReviewBatchCancellationRequest:
        row = self.db.execute(
            select(FrameworkReviewBatchCancellationRequest).where(FrameworkReviewBatchCancellationRequest.id == request_id)
        ).scalar_one_or_none()
        if row is None or row.organization_id != organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework review batch cancellation request not found")
        return row

    def approve_batch_cancellation_request(
        self,
        *,
        organization_id: uuid.UUID,
        request_id: uuid.UUID,
        approved_by_user_id: uuid.UUID,
    ) -> FrameworkReviewBatchCancellationRequest:
        row = self.get_batch_cancellation_request(organization_id=organization_id, request_id=request_id)
        if row.status != "pending":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cancellation request is not pending")
        if row.requested_by_user_id == approved_by_user_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Requester cannot approve their own cancellation request")
        row.status = "approved"
        row.approved_by_user_id = approved_by_user_id
        row.approved_at = self.now()
        self.db.flush()
        return row

    def reject_batch_cancellation_request(
        self,
        *,
        organization_id: uuid.UUID,
        request_id: uuid.UUID,
        rejected_by_user_id: uuid.UUID,
        rejection_reason: str,
    ) -> FrameworkReviewBatchCancellationRequest:
        row = self.get_batch_cancellation_request(organization_id=organization_id, request_id=request_id)
        if row.status != "pending":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cancellation request is not pending")
        if not rejection_reason.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="rejection_reason is required")
        row.status = "rejected"
        row.rejected_by_user_id = rejected_by_user_id
        row.rejected_at = self.now()
        row.rejection_reason = rejection_reason.strip()
        self.db.flush()
        return row

    def execute_batch_cancellation_request(
        self,
        *,
        organization_id: uuid.UUID,
        request_id: uuid.UUID,
        executed_by_user_id: uuid.UUID,
    ) -> tuple[FrameworkReviewBatchCancellationRequest, FrameworkReviewBatchAssignmentRun]:
        row = self.get_batch_cancellation_request(organization_id=organization_id, request_id=request_id)
        if row.status != "approved":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cancellation request is not approved")
        run = self.get_batch_assignment_run(organization_id=organization_id, run_id=row.batch_run_id)
        if run.status == "cancelled":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Batch assignment run is already cancelled")
        if self._run_has_applied_assignments(run):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Applied batch runs cannot be cancelled because assignments were already created. "
                    "Cancel individual assignments instead."
                ),
            )

        cancelled_run = self.cancel_batch_assignment_run(
            organization_id=organization_id,
            run_id=run.id,
            cancelled_by_user_id=executed_by_user_id,
            cancellation_reason=row.reason,
            enforce_approval_gate=False,
        )
        row.status = "executed"
        row.executed_by_user_id = executed_by_user_id
        row.executed_at = self.now()
        row.execution_result_json = {
            "run_id": str(cancelled_run.id),
            "run_status": cancelled_run.status,
            "cancelled_at": cancelled_run.cancelled_at.isoformat() if cancelled_run.cancelled_at else None,
            "created_assignments_count": int(cancelled_run.created_assignments_count or 0),
        }
        cancelled_run.cancellation_request_id = row.id
        self.db.flush()
        return row, cancelled_run

    def batch_assignment_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        now = self.now()
        last_30d = now - timedelta(days=30)
        total_batch_runs = int(
            self.db.execute(
                select(func.count(FrameworkReviewBatchAssignmentRun.id)).where(
                    FrameworkReviewBatchAssignmentRun.organization_id == organization_id
                )
            ).scalar_one()
        )
        applied_batch_runs = int(
            self.db.execute(
                select(func.count(FrameworkReviewBatchAssignmentRun.id)).where(
                    FrameworkReviewBatchAssignmentRun.organization_id == organization_id,
                    FrameworkReviewBatchAssignmentRun.status == "applied",
                )
            ).scalar_one()
        )
        failed_batch_runs = int(
            self.db.execute(
                select(func.count(FrameworkReviewBatchAssignmentRun.id)).where(
                    FrameworkReviewBatchAssignmentRun.organization_id == organization_id,
                    FrameworkReviewBatchAssignmentRun.status == "failed",
                )
            ).scalar_one()
        )
        cancelled_batch_runs = int(
            self.db.execute(
                select(func.count(FrameworkReviewBatchAssignmentRun.id)).where(
                    FrameworkReviewBatchAssignmentRun.organization_id == organization_id,
                    FrameworkReviewBatchAssignmentRun.status == "cancelled",
                )
            ).scalar_one()
        )
        assignments_created_last_30d = int(
            self.db.execute(
                select(func.coalesce(func.sum(FrameworkReviewBatchAssignmentRun.created_assignments_count), 0)).where(
                    FrameworkReviewBatchAssignmentRun.organization_id == organization_id,
                    FrameworkReviewBatchAssignmentRun.created_at >= last_30d,
                )
            ).scalar_one()
        )
        skipped_duplicates_last_30d = int(
            self.db.execute(
                select(func.count(FrameworkReviewBatchAssignmentItem.id)).where(
                    FrameworkReviewBatchAssignmentItem.organization_id == organization_id,
                    FrameworkReviewBatchAssignmentItem.status == "skipped_duplicate",
                    FrameworkReviewBatchAssignmentItem.created_at >= last_30d,
                )
            ).scalar_one()
        )
        failed_items_last_30d = int(
            self.db.execute(
                select(func.count(FrameworkReviewBatchAssignmentItem.id)).where(
                    FrameworkReviewBatchAssignmentItem.organization_id == organization_id,
                    FrameworkReviewBatchAssignmentItem.status == "failed",
                    FrameworkReviewBatchAssignmentItem.created_at >= last_30d,
                )
            ).scalar_one()
        )
        return {
            "total_batch_runs": total_batch_runs,
            "applied_batch_runs": applied_batch_runs,
            "failed_batch_runs": failed_batch_runs,
            "cancelled_batch_runs": cancelled_batch_runs,
            "assignments_created_last_30d": assignments_created_last_30d,
            "skipped_duplicates_last_30d": skipped_duplicates_last_30d,
            "failed_items_last_30d": failed_items_last_30d,
        }

    def list_assignment_suggestions(
        self,
        *,
        organization_id: uuid.UUID,
        framework_id: uuid.UUID,
        review_id: uuid.UUID,
    ) -> list[FrameworkReviewAssignmentSuggestion]:
        self.review_service.require_review(
            organization_id=organization_id,
            framework_id=framework_id,
            review_id=review_id,
        )
        return self.repo.list_assignment_suggestions_for_review(
            organization_id=organization_id,
            review_run_id=review_id,
        )

    def apply_assignment_suggestion(
        self,
        *,
        organization_id: uuid.UUID,
        suggestion_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        due_at: datetime | None,
        notes: str | None,
    ) -> tuple[FrameworkReviewAssignmentSuggestion, FrameworkPackReviewAssignment]:
        suggestion = self.require_assignment_suggestion(organization_id=organization_id, suggestion_id=suggestion_id)
        if suggestion.status != "open":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Suggestion must be open to apply")

        review = self.db.execute(
            select(FrameworkPackReviewRun).where(FrameworkPackReviewRun.id == suggestion.review_run_id)
        ).scalar_one_or_none()
        if review is None or review.organization_id != organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework pack review not found")

        assignment, _ = self.review_service.create_assignment(
            organization_id=organization_id,
            framework_id=review.framework_id,
            review_id=review.id,
            assigned_to_user_id=suggestion.suggested_user_id,
            assigned_by_user_id=actor_user_id,
            due_at=due_at,
            notes=notes,
            notify=False,
        )

        suggestion.status = "applied"
        suggestion.applied_by_user_id = actor_user_id
        suggestion.applied_at = self.now()
        suggestion.created_assignment_id = assignment.id
        self.db.flush()
        return suggestion, assignment

    def dismiss_assignment_suggestion(
        self,
        *,
        organization_id: uuid.UUID,
        suggestion_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        dismissal_reason: str,
    ) -> FrameworkReviewAssignmentSuggestion:
        suggestion = self.require_assignment_suggestion(organization_id=organization_id, suggestion_id=suggestion_id)
        if suggestion.status != "open":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Suggestion must be open to dismiss")
        if not dismissal_reason.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="dismissal_reason is required")
        suggestion.status = "dismissed"
        suggestion.dismissed_by_user_id = actor_user_id
        suggestion.dismissed_at = self.now()
        suggestion.dismissal_reason = dismissal_reason.strip()
        self.db.flush()
        return suggestion

    def capacity_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        snapshots = self.calculate_workload(organization_id=organization_id, persist=False)
        total_open_assignments = int(
            self.db.execute(
                select(func.count(FrameworkPackReviewAssignment.id)).where(
                    FrameworkPackReviewAssignment.organization_id == organization_id,
                    FrameworkPackReviewAssignment.status.in_(_OPEN_ASSIGNMENT_STATUSES),
                )
            ).scalar_one()
        )
        total_open_escalations = int(
            self.db.execute(
                select(func.count(FrameworkReviewEscalationEvent.id)).where(
                    FrameworkReviewEscalationEvent.organization_id == organization_id,
                    FrameworkReviewEscalationEvent.status == "open",
                )
            ).scalar_one()
        )
        open_assignment_suggestions = int(
            self.db.execute(
                select(func.count(FrameworkReviewAssignmentSuggestion.id)).where(
                    FrameworkReviewAssignmentSuggestion.organization_id == organization_id,
                    FrameworkReviewAssignmentSuggestion.status == "open",
                )
            ).scalar_one()
        )
        applied_assignment_suggestions = int(
            self.db.execute(
                select(func.count(FrameworkReviewAssignmentSuggestion.id)).where(
                    FrameworkReviewAssignmentSuggestion.organization_id == organization_id,
                    FrameworkReviewAssignmentSuggestion.status == "applied",
                )
            ).scalar_one()
        )

        active_reviewers = len(snapshots)
        overloaded_reviewers = len([item for item in snapshots if item.capacity_remaining is not None and item.capacity_remaining <= 0])
        reviewers_with_overdue_assignments = len([item for item in snapshots if item.overdue_assignments > 0])
        average_workload_score = (
            round(sum(item.workload_score for item in snapshots) / active_reviewers, 2) if active_reviewers else 0.0
        )

        return {
            "active_reviewers": active_reviewers,
            "overloaded_reviewers": overloaded_reviewers,
            "reviewers_with_overdue_assignments": reviewers_with_overdue_assignments,
            "total_open_assignments": total_open_assignments,
            "total_open_escalations": total_open_escalations,
            "average_workload_score": average_workload_score,
            "open_assignment_suggestions": open_assignment_suggestions,
            "applied_assignment_suggestions": applied_assignment_suggestions,
        }

    def simulation_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        now = self.now()
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)
        action_set = [
            "framework_reviewer_capacity.simulation_run",
            "framework_review_assignment_suggestions.simulated",
        ]
        simulations_last_24h = int(
            self.db.execute(
                select(func.count(AuditLog.id)).where(
                    AuditLog.organization_id == organization_id,
                    AuditLog.action.in_(action_set),
                    AuditLog.created_at >= last_24h,
                )
            ).scalar_one()
        )
        simulations_last_7d = int(
            self.db.execute(
                select(func.count(AuditLog.id)).where(
                    AuditLog.organization_id == organization_id,
                    AuditLog.action.in_(action_set),
                    AuditLog.created_at >= last_7d,
                )
            ).scalar_one()
        )
        return {
            "simulations_last_24h": simulations_last_24h,
            "simulations_last_7d": simulations_last_7d,
            "caveat": SIMULATION_CAVEAT,
        }
