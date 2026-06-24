import calendar
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ai_system import AISystem
from app.models.ai_system_governance_review import AISystemGovernanceReview
from app.models.ai_system_governance_review_plan_constraint import AISystemGovernanceReviewPlanConstraint
from app.models.ai_system_governance_review_plan_run import AISystemGovernanceReviewPlanRun
from app.models.ai_system_governance_review_recurrence_template import AISystemGovernanceReviewRecurrenceTemplate
from app.models.ai_system_governance_review_reminder_policy import AISystemGovernanceReviewReminderPolicy
from app.services.ai_system_service import AISystemService

REVIEW_PLAN_CAVEAT = (
    "Review-plan generation is manually triggered. CompliVibe does not autonomously create, "
    "approve, or complete AI governance reviews."
)
REVIEW_PLAN_CONSTRAINT_CAVEAT = (
    "Review-plan generation is manually triggered. Review-plan constraints are deterministic planning rules only. "
    "CompliVibe does not autonomously create, approve, or complete AI governance reviews."
)


class AISystemGovernanceRecurrenceService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def ensure_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @classmethod
    def normalize_start_from(cls, value: datetime | date | None) -> datetime:
        if value is None:
            now = cls.now()
            return datetime(now.year, now.month, now.day, tzinfo=UTC)
        if isinstance(value, datetime):
            return cls.ensure_utc(value)
        return datetime(value.year, value.month, value.day, tzinfo=UTC)

    @staticmethod
    def _add_months(value: datetime, months: int) -> datetime:
        month_index = value.month - 1 + months
        year = value.year + month_index // 12
        month = month_index % 12 + 1
        day = min(value.day, calendar.monthrange(year, month)[1])
        return value.replace(year=year, month=month, day=day)

    @classmethod
    def advance_due_at(cls, *, due_at: datetime, cadence_type: str, interval_value: int) -> datetime:
        if cadence_type == "days":
            return due_at + timedelta(days=interval_value)
        if cadence_type == "weeks":
            return due_at + timedelta(weeks=interval_value)
        if cadence_type == "months":
            return cls._add_months(due_at, interval_value)
        if cadence_type == "quarters":
            return cls._add_months(due_at, interval_value * 3)
        if cadence_type == "years":
            return cls._add_months(due_at, interval_value * 12)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported cadence_type")

    def _validate_gap_days(self, *, min_gap_days: int | None, max_gap_days: int | None) -> None:
        if min_gap_days is not None and min_gap_days < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="min_gap_days must be non-negative")
        if max_gap_days is not None and max_gap_days < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="max_gap_days must be non-negative")
        if min_gap_days is not None and max_gap_days is not None and min_gap_days > max_gap_days:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="min_gap_days must be less than or equal to max_gap_days",
            )

    def require_template(
        self,
        *,
        organization_id: uuid.UUID,
        template_id: uuid.UUID,
    ) -> AISystemGovernanceReviewRecurrenceTemplate:
        row = self.db.execute(
            select(AISystemGovernanceReviewRecurrenceTemplate).where(
                AISystemGovernanceReviewRecurrenceTemplate.id == template_id,
                AISystemGovernanceReviewRecurrenceTemplate.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI governance review recurrence template not found")
        return row

    def require_plan_run(
        self,
        *,
        organization_id: uuid.UUID,
        run_id: uuid.UUID,
    ) -> AISystemGovernanceReviewPlanRun:
        row = self.db.execute(
            select(AISystemGovernanceReviewPlanRun).where(
                AISystemGovernanceReviewPlanRun.id == run_id,
                AISystemGovernanceReviewPlanRun.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI governance review plan run not found")
        return row

    def require_constraint(
        self,
        *,
        organization_id: uuid.UUID,
        constraint_id: uuid.UUID,
    ) -> AISystemGovernanceReviewPlanConstraint:
        row = self.db.execute(
            select(AISystemGovernanceReviewPlanConstraint).where(
                AISystemGovernanceReviewPlanConstraint.id == constraint_id,
                AISystemGovernanceReviewPlanConstraint.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI governance review plan constraint not found")
        return row

    def _validate_defaults(
        self,
        *,
        organization_id: uuid.UUID,
        default_reminder_policy_id: uuid.UUID | None,
        default_assigned_to_user_id: uuid.UUID | None,
    ) -> None:
        if default_reminder_policy_id is not None:
            policy = self.db.execute(
                select(AISystemGovernanceReviewReminderPolicy).where(
                    AISystemGovernanceReviewReminderPolicy.id == default_reminder_policy_id,
                    AISystemGovernanceReviewReminderPolicy.organization_id == organization_id,
                )
            ).scalar_one_or_none()
            if policy is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Default reminder policy not found")
            if policy.status != "active":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="default_reminder_policy_id must reference an active reminder policy",
                )

        AISystemService(self.db).ensure_active_member(
            organization_id,
            default_assigned_to_user_id,
            field_name="default_assigned_to_user_id",
        )

    def create_template(
        self,
        *,
        organization_id: uuid.UUID,
        name: str,
        description: str | None,
        review_type: str,
        cadence_type: str,
        interval_value: int,
        default_reminder_policy_id: uuid.UUID | None,
        default_assigned_to_user_id: uuid.UUID | None,
        default_checklist_json: dict | list | None,
        default_description: str | None,
        status_value: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceReviewRecurrenceTemplate:
        if interval_value <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="interval_value must be positive")
        self._validate_defaults(
            organization_id=organization_id,
            default_reminder_policy_id=default_reminder_policy_id,
            default_assigned_to_user_id=default_assigned_to_user_id,
        )
        row = AISystemGovernanceReviewRecurrenceTemplate(
            organization_id=organization_id,
            name=name,
            description=description,
            review_type=review_type,
            cadence_type=cadence_type,
            interval_value=interval_value,
            default_reminder_policy_id=default_reminder_policy_id,
            default_assigned_to_user_id=default_assigned_to_user_id,
            default_checklist_json=default_checklist_json,
            default_description=default_description,
            status=status_value,
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_templates(
        self,
        *,
        organization_id: uuid.UUID,
        status_filter: str | None,
        review_type: str | None,
        include_archived: bool,
        limit: int,
        offset: int,
    ) -> list[AISystemGovernanceReviewRecurrenceTemplate]:
        stmt = select(AISystemGovernanceReviewRecurrenceTemplate).where(
            AISystemGovernanceReviewRecurrenceTemplate.organization_id == organization_id,
        )
        if status_filter:
            stmt = stmt.where(AISystemGovernanceReviewRecurrenceTemplate.status == status_filter)
        if review_type:
            stmt = stmt.where(AISystemGovernanceReviewRecurrenceTemplate.review_type == review_type)
        if not include_archived:
            stmt = stmt.where(AISystemGovernanceReviewRecurrenceTemplate.status != "archived")
        return (
            self.db.execute(
                stmt.order_by(AISystemGovernanceReviewRecurrenceTemplate.created_at.desc()).offset(offset).limit(limit)
            )
            .scalars()
            .all()
        )

    def update_template(
        self,
        *,
        row: AISystemGovernanceReviewRecurrenceTemplate,
        name: str | None,
        description: str | None,
        review_type: str | None,
        cadence_type: str | None,
        interval_value: int | None,
        default_reminder_policy_id: uuid.UUID | None,
        default_assigned_to_user_id: uuid.UUID | None,
        default_checklist_json: dict | list | None,
        default_description: str | None,
        status_value: str | None,
    ) -> AISystemGovernanceReviewRecurrenceTemplate:
        if row.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived recurrence templates cannot be updated")
        if interval_value is not None and interval_value <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="interval_value must be positive")

        self._validate_defaults(
            organization_id=row.organization_id,
            default_reminder_policy_id=default_reminder_policy_id,
            default_assigned_to_user_id=default_assigned_to_user_id,
        )

        if name is not None:
            row.name = name
        if description is not None:
            row.description = description
        if review_type is not None:
            row.review_type = review_type
        if cadence_type is not None:
            row.cadence_type = cadence_type
        if interval_value is not None:
            row.interval_value = interval_value
        if default_reminder_policy_id is not None:
            row.default_reminder_policy_id = default_reminder_policy_id
        if default_assigned_to_user_id is not None:
            row.default_assigned_to_user_id = default_assigned_to_user_id
        if default_checklist_json is not None:
            row.default_checklist_json = default_checklist_json
        if default_description is not None:
            row.default_description = default_description
        if status_value is not None:
            row.status = status_value
        self.db.flush()
        return row

    def archive_template(
        self,
        *,
        row: AISystemGovernanceReviewRecurrenceTemplate,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceReviewRecurrenceTemplate:
        row.status = "archived"
        if row.archived_at is None:
            row.archived_at = self.now()
        row.archived_by_user_id = actor_user_id
        self.db.flush()
        return row

    def create_constraint(
        self,
        *,
        organization_id: uuid.UUID,
        name: str,
        description: str | None,
        target_review_type: str,
        prerequisite_review_type: str,
        constraint_type: str,
        enforcement_mode: str,
        min_gap_days: int | None,
        max_gap_days: int | None,
        status_value: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceReviewPlanConstraint:
        self._validate_gap_days(min_gap_days=min_gap_days, max_gap_days=max_gap_days)
        row = AISystemGovernanceReviewPlanConstraint(
            organization_id=organization_id,
            name=name,
            description=description,
            target_review_type=target_review_type,
            prerequisite_review_type=prerequisite_review_type,
            constraint_type=constraint_type,
            enforcement_mode=enforcement_mode,
            min_gap_days=min_gap_days,
            max_gap_days=max_gap_days,
            status=status_value,
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_constraints(
        self,
        *,
        organization_id: uuid.UUID,
        status_filter: str | None,
        target_review_type: str | None,
        prerequisite_review_type: str | None,
        include_archived: bool,
        limit: int,
        offset: int,
    ) -> list[AISystemGovernanceReviewPlanConstraint]:
        stmt = select(AISystemGovernanceReviewPlanConstraint).where(
            AISystemGovernanceReviewPlanConstraint.organization_id == organization_id,
        )
        if status_filter:
            stmt = stmt.where(AISystemGovernanceReviewPlanConstraint.status == status_filter)
        if target_review_type:
            stmt = stmt.where(AISystemGovernanceReviewPlanConstraint.target_review_type == target_review_type)
        if prerequisite_review_type:
            stmt = stmt.where(
                AISystemGovernanceReviewPlanConstraint.prerequisite_review_type == prerequisite_review_type
            )
        if not include_archived:
            stmt = stmt.where(AISystemGovernanceReviewPlanConstraint.status != "archived")
        return (
            self.db.execute(
                stmt.order_by(AISystemGovernanceReviewPlanConstraint.created_at.desc()).offset(offset).limit(limit)
            )
            .scalars()
            .all()
        )

    def update_constraint(
        self,
        *,
        row: AISystemGovernanceReviewPlanConstraint,
        name: str | None,
        description: str | None,
        target_review_type: str | None,
        prerequisite_review_type: str | None,
        constraint_type: str | None,
        enforcement_mode: str | None,
        min_gap_days: int | None,
        max_gap_days: int | None,
        status_value: str | None,
    ) -> AISystemGovernanceReviewPlanConstraint:
        if row.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived plan constraints cannot be updated")

        effective_min = min_gap_days if min_gap_days is not None else row.min_gap_days
        effective_max = max_gap_days if max_gap_days is not None else row.max_gap_days
        self._validate_gap_days(min_gap_days=effective_min, max_gap_days=effective_max)

        if name is not None:
            row.name = name
        if description is not None:
            row.description = description
        if target_review_type is not None:
            row.target_review_type = target_review_type
        if prerequisite_review_type is not None:
            row.prerequisite_review_type = prerequisite_review_type
        if constraint_type is not None:
            row.constraint_type = constraint_type
        if enforcement_mode is not None:
            row.enforcement_mode = enforcement_mode
        if min_gap_days is not None:
            row.min_gap_days = min_gap_days
        if max_gap_days is not None:
            row.max_gap_days = max_gap_days
        if status_value is not None:
            row.status = status_value
        self.db.flush()
        return row

    def archive_constraint(
        self,
        *,
        row: AISystemGovernanceReviewPlanConstraint,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceReviewPlanConstraint:
        row.status = "archived"
        if row.archived_at is None:
            row.archived_at = self.now()
        row.archived_by_user_id = actor_user_id
        self.db.flush()
        return row

    def constraint_summary(self, *, organization_id: uuid.UUID) -> dict[str, int | dict[str, int]]:
        active_constraints = int(
            self.db.execute(
                select(func.count(AISystemGovernanceReviewPlanConstraint.id)).where(
                    AISystemGovernanceReviewPlanConstraint.organization_id == organization_id,
                    AISystemGovernanceReviewPlanConstraint.status == "active",
                )
            ).scalar_one()
        )
        inactive_constraints = int(
            self.db.execute(
                select(func.count(AISystemGovernanceReviewPlanConstraint.id)).where(
                    AISystemGovernanceReviewPlanConstraint.organization_id == organization_id,
                    AISystemGovernanceReviewPlanConstraint.status == "inactive",
                )
            ).scalar_one()
        )
        archived_constraints = int(
            self.db.execute(
                select(func.count(AISystemGovernanceReviewPlanConstraint.id)).where(
                    AISystemGovernanceReviewPlanConstraint.organization_id == organization_id,
                    AISystemGovernanceReviewPlanConstraint.status == "archived",
                )
            ).scalar_one()
        )
        block_constraints = int(
            self.db.execute(
                select(func.count(AISystemGovernanceReviewPlanConstraint.id)).where(
                    AISystemGovernanceReviewPlanConstraint.organization_id == organization_id,
                    AISystemGovernanceReviewPlanConstraint.enforcement_mode == "block",
                    AISystemGovernanceReviewPlanConstraint.status != "archived",
                )
            ).scalar_one()
        )
        warn_constraints = int(
            self.db.execute(
                select(func.count(AISystemGovernanceReviewPlanConstraint.id)).where(
                    AISystemGovernanceReviewPlanConstraint.organization_id == organization_id,
                    AISystemGovernanceReviewPlanConstraint.enforcement_mode == "warn",
                    AISystemGovernanceReviewPlanConstraint.status != "archived",
                )
            ).scalar_one()
        )
        by_type_rows = self.db.execute(
            select(AISystemGovernanceReviewPlanConstraint.constraint_type, func.count(AISystemGovernanceReviewPlanConstraint.id))
            .where(AISystemGovernanceReviewPlanConstraint.organization_id == organization_id)
            .group_by(AISystemGovernanceReviewPlanConstraint.constraint_type)
        ).all()
        by_target_rows = self.db.execute(
            select(AISystemGovernanceReviewPlanConstraint.target_review_type, func.count(AISystemGovernanceReviewPlanConstraint.id))
            .where(AISystemGovernanceReviewPlanConstraint.organization_id == organization_id)
            .group_by(AISystemGovernanceReviewPlanConstraint.target_review_type)
        ).all()
        return {
            "active_constraints": active_constraints,
            "inactive_constraints": inactive_constraints,
            "archived_constraints": archived_constraints,
            "block_constraints": block_constraints,
            "warn_constraints": warn_constraints,
            "by_constraint_type": {str(key): int(count) for key, count in by_type_rows if key is not None},
            "by_target_review_type": {str(key): int(count) for key, count in by_target_rows if key is not None},
        }

    def _target_ai_systems(
        self,
        *,
        organization_id: uuid.UUID,
        ai_system_ids: list[uuid.UUID] | None,
    ) -> list[AISystem]:
        stmt = select(AISystem).where(
            AISystem.organization_id == organization_id,
            AISystem.lifecycle_status != "archived",
        )
        if ai_system_ids is not None:
            if len(ai_system_ids) == 0:
                return []
            stmt = stmt.where(AISystem.id.in_(ai_system_ids))
        rows = self.db.execute(stmt).scalars().all()
        if ai_system_ids is not None:
            found_ids = {row.id for row in rows}
            missing = [id_ for id_ in ai_system_ids if id_ not in found_ids]
            if missing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="All ai_system_ids must belong to the organization and must not be archived",
                )
        rows.sort(key=lambda row: str(row.id))
        return rows

    def _existing_due_set(
        self,
        *,
        organization_id: uuid.UUID,
        review_type: str,
        ai_system_ids: list[uuid.UUID],
        window_start: datetime,
        window_end: datetime,
    ) -> set[tuple[uuid.UUID, datetime]]:
        if not ai_system_ids:
            return set()
        rows = (
            self.db.execute(
                select(AISystemGovernanceReview).where(
                    AISystemGovernanceReview.organization_id == organization_id,
                    AISystemGovernanceReview.review_type == review_type,
                    AISystemGovernanceReview.ai_system_id.in_(ai_system_ids),
                    AISystemGovernanceReview.status != "cancelled",
                    AISystemGovernanceReview.due_at.is_not(None),
                    AISystemGovernanceReview.due_at >= window_start,
                    AISystemGovernanceReview.due_at <= window_end,
                )
            )
            .scalars()
            .all()
        )
        return {(row.ai_system_id, self.ensure_utc(row.due_at)) for row in rows}

    def _planned_due_dates(
        self,
        *,
        start_from: datetime,
        horizon_days: int,
        cadence_type: str,
        interval_value: int,
    ) -> list[datetime]:
        end_at = start_from + timedelta(days=horizon_days)
        due_dates: list[datetime] = []
        current = start_from
        while current <= end_at:
            due_dates.append(current)
            current = self.advance_due_at(due_at=current, cadence_type=cadence_type, interval_value=interval_value)
        return due_dates

    def _select_constraints(
        self,
        *,
        organization_id: uuid.UUID,
        target_review_type: str,
        apply_constraints: bool,
        constraint_ids: list[uuid.UUID] | None,
    ) -> list[AISystemGovernanceReviewPlanConstraint]:
        if not apply_constraints:
            return []

        if constraint_ids:
            rows = (
                self.db.execute(
                    select(AISystemGovernanceReviewPlanConstraint).where(
                        AISystemGovernanceReviewPlanConstraint.organization_id == organization_id,
                        AISystemGovernanceReviewPlanConstraint.id.in_(constraint_ids),
                    )
                )
                .scalars()
                .all()
            )
            found = {row.id for row in rows}
            missing = [item for item in constraint_ids if item not in found]
            if missing:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more constraint_ids not found")

            selected: list[AISystemGovernanceReviewPlanConstraint] = []
            for row in rows:
                if row.status != "active":
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected constraints must be active")
                if row.target_review_type != target_review_type:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Selected constraints must match template review_type",
                    )
                selected.append(row)
            selected.sort(key=lambda row: str(row.id))
            return selected

        rows = (
            self.db.execute(
                select(AISystemGovernanceReviewPlanConstraint)
                .where(
                    AISystemGovernanceReviewPlanConstraint.organization_id == organization_id,
                    AISystemGovernanceReviewPlanConstraint.status == "active",
                    AISystemGovernanceReviewPlanConstraint.target_review_type == target_review_type,
                )
                .order_by(AISystemGovernanceReviewPlanConstraint.created_at.asc())
            )
            .scalars()
            .all()
        )
        return rows

    @staticmethod
    def _prerequisite_reference(review: AISystemGovernanceReview) -> datetime:
        if review.completed_at is not None:
            return review.completed_at
        if review.due_at is not None:
            return review.due_at
        return review.created_at

    def _evaluate_constraint(
        self,
        *,
        organization_id: uuid.UUID,
        ai_system_id: uuid.UUID,
        planned_due_at: datetime,
        constraint: AISystemGovernanceReviewPlanConstraint,
    ) -> dict[str, Any]:
        rows = (
            self.db.execute(
                select(AISystemGovernanceReview).where(
                    AISystemGovernanceReview.organization_id == organization_id,
                    AISystemGovernanceReview.ai_system_id == ai_system_id,
                    AISystemGovernanceReview.review_type == constraint.prerequisite_review_type,
                    AISystemGovernanceReview.status == "completed",
                )
            )
            .scalars()
            .all()
        )
        references = sorted([self.ensure_utc(self._prerequisite_reference(row)) for row in rows])
        references = [ref for ref in references if ref <= planned_due_at]

        result: dict[str, Any] = {
            "constraint_id": str(constraint.id),
            "name": constraint.name,
            "constraint_type": constraint.constraint_type,
            "enforcement_mode": constraint.enforcement_mode,
            "passed": True,
            "reason": None,
            "warning": False,
        }

        if not references:
            result["passed"] = False
            result["reason"] = "missing_completed_prerequisite"
            result["warning"] = constraint.enforcement_mode == "warn"
            return result

        if constraint.constraint_type == "prerequisite_completed":
            return result

        latest = references[-1]
        gap_days = max(0, (planned_due_at.date() - latest.date()).days)
        result["gap_days"] = gap_days

        if constraint.min_gap_days is not None and gap_days < constraint.min_gap_days:
            result["passed"] = False
            result["reason"] = "min_gap_not_satisfied"
        if constraint.max_gap_days is not None and gap_days > constraint.max_gap_days:
            result["passed"] = False
            result["reason"] = "max_gap_exceeded"

        if result["passed"] is False:
            result["warning"] = constraint.enforcement_mode == "warn"
        return result

    def generate_plan(
        self,
        *,
        organization_id: uuid.UUID,
        template: AISystemGovernanceReviewRecurrenceTemplate,
        dry_run: bool,
        horizon_days: int,
        ai_system_ids: list[uuid.UUID] | None,
        start_from: datetime | date | None,
        actor_user_id: uuid.UUID,
        apply_constraints: bool,
        constraint_ids: list[uuid.UUID] | None,
    ) -> dict[str, Any]:
        if template.status != "active":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Recurrence template must be active")

        start_at = self.normalize_start_from(start_from)
        targets = self._target_ai_systems(organization_id=organization_id, ai_system_ids=ai_system_ids)
        target_ids = [row.id for row in targets]
        due_dates = self._planned_due_dates(
            start_from=start_at,
            horizon_days=horizon_days,
            cadence_type=template.cadence_type,
            interval_value=template.interval_value,
        )

        existing = self._existing_due_set(
            organization_id=organization_id,
            review_type=template.review_type,
            ai_system_ids=target_ids,
            window_start=due_dates[0] if due_dates else start_at,
            window_end=due_dates[-1] if due_dates else start_at,
        )

        constraints = self._select_constraints(
            organization_id=organization_id,
            target_review_type=template.review_type,
            apply_constraints=apply_constraints,
            constraint_ids=constraint_ids,
        )

        planned_reviews: list[dict[str, Any]] = []
        skipped_reviews: list[dict[str, Any]] = []
        created_count = 0

        for ai_system in targets:
            for due_at in due_dates:
                key = (ai_system.id, due_at)
                if key in existing:
                    skipped_reviews.append(
                        {
                            "ai_system_id": ai_system.id,
                            "review_type": template.review_type,
                            "due_at": due_at,
                            "reason": "duplicate_existing_review",
                            "constraint_results": [],
                        }
                    )
                    continue

                constraint_results = [
                    self._evaluate_constraint(
                        organization_id=organization_id,
                        ai_system_id=ai_system.id,
                        planned_due_at=due_at,
                        constraint=constraint,
                    )
                    for constraint in constraints
                ]
                has_block_failure = any(
                    (result["passed"] is False and result["enforcement_mode"] == "block")
                    for result in constraint_results
                )

                if has_block_failure:
                    skipped_reviews.append(
                        {
                            "ai_system_id": ai_system.id,
                            "review_type": template.review_type,
                            "due_at": due_at,
                            "reason": "constraint_blocked",
                            "constraint_results": constraint_results,
                        }
                    )
                    continue

                item = {
                    "ai_system_id": ai_system.id,
                    "review_type": template.review_type,
                    "title": template.name,
                    "due_at": due_at,
                    "assigned_to_user_id": template.default_assigned_to_user_id,
                    "reminder_policy_id": template.default_reminder_policy_id,
                    "constraint_results": constraint_results,
                }
                planned_reviews.append(item)

                if not dry_run:
                    row = AISystemGovernanceReview(
                        organization_id=organization_id,
                        ai_system_id=ai_system.id,
                        review_type=template.review_type,
                        status="pending",
                        outcome=None,
                        title=template.name,
                        description=template.default_description,
                        checklist_json=template.default_checklist_json,
                        requested_by_user_id=actor_user_id,
                        assigned_to_user_id=template.default_assigned_to_user_id,
                        caveat=(
                            "This governance review is a manual internal CompliVibe governance checkpoint. "
                            "It is not legal advice, regulatory approval, or certification."
                        ),
                        due_at=due_at,
                        reminder_policy_id=template.default_reminder_policy_id,
                    )
                    self.db.add(row)
                    created_count += 1
                    existing.add(key)

        caveat = REVIEW_PLAN_CONSTRAINT_CAVEAT if apply_constraints else REVIEW_PLAN_CAVEAT
        result_json = {
            "dry_run": dry_run,
            "template_id": str(template.id),
            "horizon_days": horizon_days,
            "planned_count": len(planned_reviews),
            "created_count": 0 if dry_run else created_count,
            "skipped_count": len(skipped_reviews),
            "apply_constraints": apply_constraints,
            "constraint_ids": [str(item.id) for item in constraints],
            "planned_reviews": [
                {
                    "ai_system_id": str(item["ai_system_id"]),
                    "review_type": item["review_type"],
                    "title": item["title"],
                    "due_at": item["due_at"].isoformat(),
                    "assigned_to_user_id": str(item["assigned_to_user_id"]) if item["assigned_to_user_id"] else None,
                    "reminder_policy_id": str(item["reminder_policy_id"]) if item["reminder_policy_id"] else None,
                    "constraint_results": item["constraint_results"],
                }
                for item in planned_reviews
            ],
            "skipped_reviews": [
                {
                    "ai_system_id": str(item["ai_system_id"]),
                    "review_type": item["review_type"],
                    "due_at": item["due_at"].isoformat(),
                    "reason": item["reason"],
                    "constraint_results": item["constraint_results"],
                }
                for item in skipped_reviews
            ],
            "caveat": caveat,
        }

        run = AISystemGovernanceReviewPlanRun(
            organization_id=organization_id,
            template_id=template.id,
            status="previewed" if dry_run else "applied",
            dry_run=dry_run,
            horizon_days=horizon_days,
            target_ai_system_ids_json=[str(item) for item in target_ids] if ai_system_ids is not None else None,
            generated_reviews_count=len(planned_reviews) if dry_run else created_count,
            skipped_reviews_count=len(skipped_reviews),
            result_json=result_json,
            requested_by_user_id=actor_user_id,
        )
        self.db.add(run)
        self.db.flush()

        return {
            "dry_run": dry_run,
            "template_id": template.id,
            "horizon_days": horizon_days,
            "planned_count": len(planned_reviews),
            "created_count": 0 if dry_run else created_count,
            "skipped_count": len(skipped_reviews),
            "planned_reviews": planned_reviews,
            "skipped_reviews": skipped_reviews,
            "run_id": run.id,
            "caveat": caveat,
        }

    def list_plan_runs(
        self,
        *,
        organization_id: uuid.UUID,
        template_id: uuid.UUID | None,
        status_filter: str | None,
        dry_run: bool | None,
        limit: int,
        offset: int,
    ) -> list[AISystemGovernanceReviewPlanRun]:
        stmt = select(AISystemGovernanceReviewPlanRun).where(
            AISystemGovernanceReviewPlanRun.organization_id == organization_id,
        )
        if template_id is not None:
            stmt = stmt.where(AISystemGovernanceReviewPlanRun.template_id == template_id)
        if status_filter:
            stmt = stmt.where(AISystemGovernanceReviewPlanRun.status == status_filter)
        if dry_run is not None:
            stmt = stmt.where(AISystemGovernanceReviewPlanRun.dry_run == dry_run)
        return (
            self.db.execute(
                stmt.order_by(AISystemGovernanceReviewPlanRun.created_at.desc()).offset(offset).limit(limit)
            )
            .scalars()
            .all()
        )

    def recurrence_summary(self, *, organization_id: uuid.UUID) -> dict[str, int]:
        now = self.now()
        since = now - timedelta(days=30)

        active_templates = int(
            self.db.execute(
                select(func.count(AISystemGovernanceReviewRecurrenceTemplate.id)).where(
                    AISystemGovernanceReviewRecurrenceTemplate.organization_id == organization_id,
                    AISystemGovernanceReviewRecurrenceTemplate.status == "active",
                )
            ).scalar_one()
        )
        inactive_templates = int(
            self.db.execute(
                select(func.count(AISystemGovernanceReviewRecurrenceTemplate.id)).where(
                    AISystemGovernanceReviewRecurrenceTemplate.organization_id == organization_id,
                    AISystemGovernanceReviewRecurrenceTemplate.status == "inactive",
                )
            ).scalar_one()
        )
        archived_templates = int(
            self.db.execute(
                select(func.count(AISystemGovernanceReviewRecurrenceTemplate.id)).where(
                    AISystemGovernanceReviewRecurrenceTemplate.organization_id == organization_id,
                    AISystemGovernanceReviewRecurrenceTemplate.status == "archived",
                )
            ).scalar_one()
        )
        plan_runs = int(
            self.db.execute(
                select(func.count(AISystemGovernanceReviewPlanRun.id)).where(
                    AISystemGovernanceReviewPlanRun.organization_id == organization_id,
                )
            ).scalar_one()
        )
        applied_plan_runs = int(
            self.db.execute(
                select(func.count(AISystemGovernanceReviewPlanRun.id)).where(
                    AISystemGovernanceReviewPlanRun.organization_id == organization_id,
                    AISystemGovernanceReviewPlanRun.status == "applied",
                )
            ).scalar_one()
        )
        previewed_plan_runs = int(
            self.db.execute(
                select(func.count(AISystemGovernanceReviewPlanRun.id)).where(
                    AISystemGovernanceReviewPlanRun.organization_id == organization_id,
                    AISystemGovernanceReviewPlanRun.status == "previewed",
                )
            ).scalar_one()
        )

        recent_runs = (
            self.db.execute(
                select(AISystemGovernanceReviewPlanRun).where(
                    AISystemGovernanceReviewPlanRun.organization_id == organization_id,
                    AISystemGovernanceReviewPlanRun.created_at >= since,
                )
            )
            .scalars()
            .all()
        )

        return {
            "active_templates": active_templates,
            "inactive_templates": inactive_templates,
            "archived_templates": archived_templates,
            "plan_runs": plan_runs,
            "applied_plan_runs": applied_plan_runs,
            "previewed_plan_runs": previewed_plan_runs,
            "generated_reviews_last_30d": int(sum(row.generated_reviews_count for row in recent_runs)),
            "skipped_reviews_last_30d": int(sum(row.skipped_reviews_count for row in recent_runs)),
        }
