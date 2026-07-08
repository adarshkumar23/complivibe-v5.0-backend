from __future__ import annotations

import uuid
from datetime import datetime, timezone

from dateutil.relativedelta import relativedelta
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.bcm import BiaAssessment, BusinessProcess
from app.models.membership import Membership
from app.models.user import User

# Common DR/BCM practice ceilings: tier_1_critical processes are expected to
# recover within a business day, tier_2_high within a business week. These
# are advisory (surfaced as context flags, not enforced as hard errors) since
# an organization's actual DR capability may legitimately differ.
_RTO_CEILING_HOURS_BY_TIER = {"tier_1_critical": 24, "tier_2_high": 72}
_LOW_IMPACT_TIERS_FOR_CRITICAL_PROCESS = {"low"}


class BcmService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Business processes
    # ------------------------------------------------------------------
    def _validate_org_user(self, user_id: uuid.UUID | None, organization_id: uuid.UUID, *, field_name: str) -> None:
        if user_id is None:
            return
        user = self.db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_name} does not reference an existing user")
        membership = self.db.execute(
            select(Membership).where(Membership.user_id == user_id, Membership.organization_id == organization_id)
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_name} does not belong to this organization")
        if membership.status != "active" or not user.is_active or user.status != "active":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_name} must be an active organization member")

    @staticmethod
    def _validate_no_self_dependency(process_name: str, dependencies_json: list[dict] | None) -> None:
        if not dependencies_json:
            return
        normalized_name = process_name.strip().lower()
        for entry in dependencies_json:
            if entry.get("type") == "process" and str(entry.get("name", "")).strip().lower() == normalized_name:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A process cannot list itself as a dependency",
                )

    def create_process(self, organization_id: uuid.UUID, *, data: dict, created_by_user_id: uuid.UUID | None) -> BusinessProcess:
        self._validate_org_user(data.get("owner_user_id"), organization_id, field_name="owner_user_id")
        self._validate_no_self_dependency(data.get("name", ""), data.get("dependencies_json"))
        process = BusinessProcess(
            organization_id=organization_id,
            created_by_user_id=created_by_user_id,
            **data,
        )
        self.db.add(process)
        self.db.flush()
        return process

    def get_process(self, organization_id: uuid.UUID, process_id: uuid.UUID) -> BusinessProcess:
        process = self.db.execute(
            select(BusinessProcess).where(
                BusinessProcess.id == process_id, BusinessProcess.organization_id == organization_id
            )
        ).scalar_one_or_none()
        if process is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business process not found in this organization")
        return process

    def list_processes(self, organization_id: uuid.UUID) -> list[BusinessProcess]:
        return list(
            self.db.execute(
                select(BusinessProcess)
                .where(BusinessProcess.organization_id == organization_id)
                .order_by(BusinessProcess.created_at.desc())
            ).scalars()
        )

    def update_process(self, organization_id: uuid.UUID, process_id: uuid.UUID, *, data: dict) -> BusinessProcess:
        process = self.get_process(organization_id, process_id)
        if "owner_user_id" in data:
            self._validate_org_user(data["owner_user_id"], organization_id, field_name="owner_user_id")
        effective_name = data.get("name", process.name)
        effective_dependencies = data.get("dependencies_json", process.dependencies_json)
        self._validate_no_self_dependency(effective_name, effective_dependencies)
        for key, value in data.items():
            setattr(process, key, value)
        self.db.flush()
        return process

    # ------------------------------------------------------------------
    # BIA assessments
    # ------------------------------------------------------------------
    def create_bia_assessment(
        self,
        organization_id: uuid.UUID,
        process_id: uuid.UUID,
        *,
        data: dict,
    ) -> BiaAssessment:
        # Ensures the process exists and belongs to this org (404 otherwise).
        self.get_process(organization_id, process_id)
        if data.get("reviewed_by_user_id") is not None:
            self._validate_org_user(data["reviewed_by_user_id"], organization_id, field_name="reviewed_by_user_id")

        # last_reviewed_at/reviewed_by_user_id are only ever set here when the caller
        # explicitly provides both (enforced together by BiaAssessmentCreateRequest's
        # model_validator) -- a freshly-created BIA with neither provided genuinely
        # has last_reviewed_at = None ("never reviewed"), not an auto-stamped "now".
        bia = BiaAssessment(
            organization_id=organization_id,
            process_id=process_id,
            **data,
        )
        self.db.add(bia)
        self.db.flush()
        return bia

    def get_latest_bia(self, organization_id: uuid.UUID, process_id: uuid.UUID) -> BiaAssessment | None:
        # Ordered by created_at (always populated) rather than last_reviewed_at (which
        # can now be null for a never-reviewed BIA, and doesn't necessarily track
        # record recency anyway -- e.g. backfilling a years-old review date on a
        # record created today). created_at reflects which BIA document is actually
        # the current one for this process.
        return self.db.execute(
            select(BiaAssessment)
            .where(BiaAssessment.organization_id == organization_id, BiaAssessment.process_id == process_id)
            .order_by(BiaAssessment.created_at.desc())
        ).scalars().first()

    def list_bia_history(self, organization_id: uuid.UUID, process_id: uuid.UUID) -> list[BiaAssessment]:
        return list(
            self.db.execute(
                select(BiaAssessment)
                .where(BiaAssessment.organization_id == organization_id, BiaAssessment.process_id == process_id)
                .order_by(BiaAssessment.created_at.desc())
            ).scalars()
        )

    # ------------------------------------------------------------------
    # Staleness
    # ------------------------------------------------------------------
    def compute_staleness(
        self,
        process: BusinessProcess,
        bia: BiaAssessment | None,
        owner_user: User | None,
    ) -> dict:
        reasons: list[str] = []

        if bia is None:
            reasons.append("No BIA assessment has ever been completed for this process")
        elif bia.last_reviewed_at is None:
            # A BIA record exists but has never actually been reviewed (last_reviewed_at
            # is only ever set by a genuine review action -- see G9 item 21). This must
            # be flagged at least as urgently as "no BIA exists", not silently treated
            # as fresh just because a record is present.
            reasons.append("BIA assessment exists but has never been reviewed")
        else:
            last_reviewed_at = bia.last_reviewed_at
            if last_reviewed_at.tzinfo is None:
                last_reviewed_at = last_reviewed_at.replace(tzinfo=timezone.utc)
            # Use dateutil.relativedelta for accurate calendar-month arithmetic
            # (available transitively via python-dateutil in this repo's env).
            due_at = last_reviewed_at + relativedelta(months=bia.review_frequency_months)
            now = datetime.now(timezone.utc)
            if now > due_at:
                overdue_days = (now - due_at).days
                reasons.append(
                    f"BIA review overdue by {overdue_days} days "
                    f"(last reviewed {last_reviewed_at.date().isoformat()}, "
                    f"review frequency {bia.review_frequency_months} months)"
                )

        if owner_user is not None and (not owner_user.is_active or owner_user.status != "active"):
            reasons.append("Process owner account is deactivated")
        if process.owner_user_id is not None:
            owner_membership = self.db.execute(
                select(Membership).where(
                    Membership.user_id == process.owner_user_id,
                    Membership.organization_id == process.organization_id,
                )
            ).scalar_one_or_none()
            if owner_membership is None or owner_membership.status != "active":
                reasons.append("Process owner organization membership is inactive")

        return {"is_stale": len(reasons) > 0, "stale_reasons": reasons}

    def list_overdue_reviews(self, organization_id: uuid.UUID) -> list[dict]:
        # Archived processes are no longer operating, so continuity review
        # cadence no longer applies to them -- only active processes are
        # candidates for a "review overdue" finding.
        processes = [p for p in self.list_processes(organization_id) if p.status == "active"]
        results: list[dict] = []
        for process in processes:
            bia = self.get_latest_bia(organization_id, process.id)
            owner_user = self.db.get(User, process.owner_user_id) if process.owner_user_id else None
            staleness = self.compute_staleness(process, bia, owner_user)
            if staleness["is_stale"]:
                results.append(
                    {
                        "process_id": process.id,
                        "process_name": process.name,
                        "criticality_tier": process.criticality_tier,
                        "latest_bia": bia,
                        "is_stale": staleness["is_stale"],
                        "stale_reasons": staleness["stale_reasons"],
                    }
                )
        return results

    # ------------------------------------------------------------------
    # Intelligence: BIA quality/consistency signals
    # ------------------------------------------------------------------
    def build_bia_context(
        self,
        organization_id: uuid.UUID,
        process: BusinessProcess,
        bia: BiaAssessment | None,
    ) -> dict:
        """Surface insight beyond the raw BIA record: DR-practice consistency
        checks, appetite-style ceilings, and dependency-chain freshness --
        plus the staleness engine already used by the overdue-reviews list,
        so a single process's BIA view carries the same signal.
        """
        owner_user = self.db.get(User, process.owner_user_id) if process.owner_user_id else None
        staleness = self.compute_staleness(process, bia, owner_user)
        flags: list[str] = list(staleness["stale_reasons"])

        ceiling = _RTO_CEILING_HOURS_BY_TIER.get(process.criticality_tier)
        if ceiling is not None and process.recovery_time_objective_hours > ceiling:
            flags.append(
                f"recovery_time_objective_exceeds_recommended_ceiling_for_{process.criticality_tier} "
                f"(RTO={process.recovery_time_objective_hours}h, recommended<={ceiling}h)"
            )

        if bia is not None and bia.financial_impact_tier is not None:
            if (
                process.criticality_tier == "tier_1_critical"
                and bia.financial_impact_tier in _LOW_IMPACT_TIERS_FOR_CRITICAL_PROCESS
            ):
                flags.append(
                    "financial_impact_tier_inconsistent_with_process_criticality "
                    f"(process is {process.criticality_tier} but BIA rates financial impact "
                    f"'{bia.financial_impact_tier}')"
                )

        if process.dependencies_json:
            active_process_names = {
                p.name.strip().lower()
                for p in self.list_processes(organization_id)
                if p.status == "active"
            }
            for entry in process.dependencies_json:
                if entry.get("type") != "process":
                    continue
                dep_name = str(entry.get("name", "")).strip().lower()
                if dep_name and dep_name not in active_process_names:
                    flags.append(
                        f"dependency_process_not_found_or_inactive: '{entry.get('name')}'"
                    )

        return {"is_stale": staleness["is_stale"], "context_flags": sorted(set(flags))}
