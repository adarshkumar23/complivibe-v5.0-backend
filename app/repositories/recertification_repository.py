import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.evidence_recertification_policy import EvidenceRecertificationPolicy
from app.models.recertification_action_log import RecertificationActionLog
from app.models.recertification_run import RecertificationRun


class RecertificationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_policy(self, policy_id: uuid.UUID) -> EvidenceRecertificationPolicy | None:
        return self.db.execute(select(EvidenceRecertificationPolicy).where(EvidenceRecertificationPolicy.id == policy_id)).scalar_one_or_none()

    def list_policies(self, organization_id: uuid.UUID) -> list[EvidenceRecertificationPolicy]:
        return list(
            self.db.execute(
                select(EvidenceRecertificationPolicy)
                .where(EvidenceRecertificationPolicy.organization_id == organization_id)
                .order_by(EvidenceRecertificationPolicy.created_at.desc())
            ).scalars().all()
        )

    def list_runs(
        self,
        organization_id: uuid.UUID,
        *,
        run_type: str | None,
        status: str | None,
        policy_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> list[RecertificationRun]:
        stmt = select(RecertificationRun).where(RecertificationRun.organization_id == organization_id)
        if run_type:
            stmt = stmt.where(RecertificationRun.run_type == run_type)
        if status:
            stmt = stmt.where(RecertificationRun.status == status)
        if policy_id:
            stmt = stmt.where(RecertificationRun.policy_id == policy_id)

        return list(
            self.db.execute(
                stmt.order_by(RecertificationRun.started_at.desc()).offset(offset).limit(limit)
            ).scalars().all()
        )

    def get_run(self, run_id: uuid.UUID) -> RecertificationRun | None:
        return self.db.execute(select(RecertificationRun).where(RecertificationRun.id == run_id)).scalar_one_or_none()

    def list_action_logs(self, organization_id: uuid.UUID, run_id: uuid.UUID) -> list[RecertificationActionLog]:
        return list(
            self.db.execute(
                select(RecertificationActionLog)
                .where(
                    RecertificationActionLog.organization_id == organization_id,
                    RecertificationActionLog.run_id == run_id,
                )
                .order_by(RecertificationActionLog.created_at.asc())
            ).scalars().all()
        )
