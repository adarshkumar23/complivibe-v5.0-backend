from __future__ import annotations

import uuid
from datetime import datetime, timezone

from dateutil.relativedelta import relativedelta
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.bcm import BiaAssessment, BusinessProcess
from app.models.user import User


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
        # A user only "belongs" to the org via a membership record; check that.
        from app.models.membership import Membership

        membership = self.db.execute(
            select(Membership).where(Membership.user_id == user_id, Membership.organization_id == organization_id)
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_name} does not belong to this organization")

    def create_process(self, organization_id: uuid.UUID, *, data: dict, created_by_user_id: uuid.UUID | None) -> BusinessProcess:
        self._validate_org_user(data.get("owner_user_id"), organization_id, field_name="owner_user_id")
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

        kwargs = dict(data)
        if kwargs.get("last_reviewed_at") is None:
            kwargs.pop("last_reviewed_at", None)

        bia = BiaAssessment(
            organization_id=organization_id,
            process_id=process_id,
            **kwargs,
        )
        self.db.add(bia)
        self.db.flush()
        return bia

    def get_latest_bia(self, organization_id: uuid.UUID, process_id: uuid.UUID) -> BiaAssessment | None:
        return self.db.execute(
            select(BiaAssessment)
            .where(BiaAssessment.organization_id == organization_id, BiaAssessment.process_id == process_id)
            .order_by(BiaAssessment.last_reviewed_at.desc(), BiaAssessment.created_at.desc())
        ).scalars().first()

    def list_bia_history(self, organization_id: uuid.UUID, process_id: uuid.UUID) -> list[BiaAssessment]:
        return list(
            self.db.execute(
                select(BiaAssessment)
                .where(BiaAssessment.organization_id == organization_id, BiaAssessment.process_id == process_id)
                .order_by(BiaAssessment.last_reviewed_at.desc(), BiaAssessment.created_at.desc())
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

        if owner_user is not None and not owner_user.is_active:
            reasons.append("Process owner account is deactivated")

        return {"is_stale": len(reasons) > 0, "stale_reasons": reasons}

    def list_overdue_reviews(self, organization_id: uuid.UUID) -> list[dict]:
        processes = self.list_processes(organization_id)
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
