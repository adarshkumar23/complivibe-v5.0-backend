import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.business_unit import BusinessUnit
from app.models.training_completion_record import TrainingCompletionRecord
from app.schemas.training_analytics import (
    BusinessUnitTrainingSummary,
    OverdueTrainingDetail,
    TrainingAnalyticsSummaryResponse,
    TrainingCompletionRecordComplete,
    TrainingCompletionRecordCreate,
)
from app.services.audit_service import AuditService

# --- "Trending toward non-compliance" rule -------------------------------------------------
#
# A business-unit bucket is flagged when BOTH conditions hold:
#   1. Minimum sample size: total_assigned >= MIN_SAMPLE_SIZE_FOR_FLAGGING.
#      Buckets smaller than this are too noisy for a single overdue record to be meaningful
#      (e.g. 1 overdue out of 1 assigned is a 100% overdue rate but tells us nothing about a trend).
#   2. Its overdue_rate exceeds max(org_overdue_rate * RELATIVE_MULTIPLIER, ABSOLUTE_FLOOR_PCT):
#        - The relative term (1.5x org average) flags units performing meaningfully worse than
#          their peers, which is what "trending" means -- worse than the rest of the org, not just
#          a coincidental blip. It's proportional so it scales as the whole org's completion posture
#          drifts, rather than a number picked without justification.
#        - The absolute floor (25%) guards the case where org-wide overdue rate is itself already
#          low (e.g. 2%) -- a 1.5x multiplier of a near-zero baseline would flag almost nothing,
#          hiding the fact that a full quarter of one BU's assigned trainings are overdue. It also
#          guards the reverse: if org overdue rate is already very high, we only escalate a subset.
#      Both terms are intentionally simple/auditable rather than a statistical model, since this
#      is meant to be explained to a compliance officer in one sentence.
MIN_SAMPLE_SIZE_FOR_FLAGGING = 3
RELATIVE_MULTIPLIER = 1.5
ABSOLUTE_FLOOR_PCT = 25.0

TRENDING_RULE_NOTE = (
    f"A business unit is flagged 'trending toward non-compliance' when it has at least "
    f"{MIN_SAMPLE_SIZE_FOR_FLAGGING} assigned trainings AND its overdue rate exceeds "
    f"max(org_overdue_rate * {RELATIVE_MULTIPLIER}, {ABSOLUTE_FLOOR_PCT}%)."
)


class TrainingAnalyticsService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _comparable(dt: datetime) -> datetime:
        """Normalize a datetime for cross-dialect comparison.

        SQLite (used in tests) does not preserve tzinfo on DateTime(timezone=True)
        columns -- values round-trip as naive datetimes. Postgres (production) does
        preserve tzinfo. To compare "is this due_date in the past" safely regardless
        of dialect, strip tzinfo (converting to UTC first if present) before comparing.
        """
        if dt.tzinfo is not None:
            return dt.astimezone(UTC).replace(tzinfo=None)
        return dt

    def _business_unit_in_org(self, org_id: uuid.UUID, business_unit_id: uuid.UUID) -> None:
        row = self.db.execute(
            select(BusinessUnit.id).where(
                BusinessUnit.organization_id == org_id,
                BusinessUnit.id == business_unit_id,
                BusinessUnit.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business unit not found")

    def create_record(
        self, org_id: uuid.UUID, data: TrainingCompletionRecordCreate, created_by: uuid.UUID | None
    ) -> TrainingCompletionRecord:
        if data.business_unit_id is not None:
            self._business_unit_in_org(org_id, data.business_unit_id)

        row = TrainingCompletionRecord(
            organization_id=org_id,
            user_id=data.user_id,
            business_unit_id=data.business_unit_id,
            training_type=data.training_type,
            assigned_at=data.assigned_at or self.utcnow(),
            due_date=data.due_date,
            score=data.score,
            created_by=created_by,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="training_completion_record.created",
            entity_type="training_completion_record",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={
                "user_id": str(row.user_id),
                "business_unit_id": str(row.business_unit_id) if row.business_unit_id else None,
                "training_type": row.training_type,
                "due_date": row.due_date.isoformat(),
            },
            metadata_json={"source": "api"},
        )
        return row

    def get_record(self, org_id: uuid.UUID, record_id: uuid.UUID) -> TrainingCompletionRecord:
        row = self.db.execute(
            select(TrainingCompletionRecord).where(
                TrainingCompletionRecord.organization_id == org_id,
                TrainingCompletionRecord.id == record_id,
                TrainingCompletionRecord.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training completion record not found")
        return row

    def list_records(
        self,
        org_id: uuid.UUID,
        *,
        business_unit_id: uuid.UUID | None = None,
        training_type: str | None = None,
        completed: bool | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[TrainingCompletionRecord]:
        stmt = select(TrainingCompletionRecord).where(
            TrainingCompletionRecord.organization_id == org_id,
            TrainingCompletionRecord.deleted_at.is_(None),
        )
        if business_unit_id is not None:
            stmt = stmt.where(TrainingCompletionRecord.business_unit_id == business_unit_id)
        if training_type is not None:
            stmt = stmt.where(TrainingCompletionRecord.training_type == training_type)
        if completed is True:
            stmt = stmt.where(TrainingCompletionRecord.completed_at.isnot(None))
        elif completed is False:
            stmt = stmt.where(TrainingCompletionRecord.completed_at.is_(None))

        stmt = stmt.order_by(TrainingCompletionRecord.due_date.asc()).offset(skip).limit(limit)
        return self.db.execute(stmt).scalars().all()

    def complete_record(
        self,
        org_id: uuid.UUID,
        record_id: uuid.UUID,
        data: TrainingCompletionRecordComplete,
        actor_id: uuid.UUID | None = None,
    ) -> TrainingCompletionRecord:
        # Idempotent re-completion is allowed: re-submitting a completion (e.g. an updated score
        # from a retake, or a correction) simply overwrites completed_at/score rather than
        # rejecting with a conflict. There is no downstream state (like campaign counts) that
        # depends on completion being a one-way transition, so rejecting a second call would only
        # add friction for legitimate corrections.
        row = self.get_record(org_id, record_id)
        before = {
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "score": row.score,
        }
        row.completed_at = data.completed_at or self.utcnow()
        if data.score is not None:
            row.score = data.score
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="training_completion_record.completed",
            entity_type="training_completion_record",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            before_json=before,
            after_json={
                "completed_at": row.completed_at.isoformat(),
                "score": row.score,
            },
            metadata_json={"source": "api"},
        )
        return row

    def get_summary(self, org_id: uuid.UUID) -> TrainingAnalyticsSummaryResponse:
        now = self.utcnow()
        now_cmp = self._comparable(now)
        rows = self.db.execute(
            select(TrainingCompletionRecord).where(
                TrainingCompletionRecord.organization_id == org_id,
                TrainingCompletionRecord.deleted_at.is_(None),
            )
        ).scalars().all()

        bu_ids = {r.business_unit_id for r in rows if r.business_unit_id is not None}
        bu_names: dict[uuid.UUID, str] = {}
        if bu_ids:
            bu_rows = self.db.execute(
                select(BusinessUnit.id, BusinessUnit.name).where(
                    BusinessUnit.organization_id == org_id,
                    BusinessUnit.id.in_(bu_ids),
                )
            ).all()
            bu_names = {r[0]: r[1] for r in bu_rows}

        buckets: dict[uuid.UUID | None, list[TrainingCompletionRecord]] = {}
        for r in rows:
            buckets.setdefault(r.business_unit_id, []).append(r)

        total_assigned = len(rows)
        total_completed = sum(1 for r in rows if r.completed_at is not None)
        overall_overdue_count = sum(
            1 for r in rows if r.completed_at is None and self._comparable(r.due_date) < now_cmp
        )
        overall_overdue_rate = (overall_overdue_count / total_assigned * 100.0) if total_assigned else 0.0
        overall_completion_rate = (total_completed / total_assigned * 100.0) if total_assigned else 0.0

        threshold = max(overall_overdue_rate * RELATIVE_MULTIPLIER, ABSOLUTE_FLOOR_PCT)

        bu_summaries: list[BusinessUnitTrainingSummary] = []
        for bu_id, bu_rows in sorted(buckets.items(), key=lambda kv: (kv[0] is None, str(kv[0]))):
            bucket_total = len(bu_rows)
            bucket_completed = sum(1 for r in bu_rows if r.completed_at is not None)
            overdue_rows = [
                r for r in bu_rows if r.completed_at is None and self._comparable(r.due_date) < now_cmp
            ]
            bucket_overdue = len(overdue_rows)
            bucket_completion_rate = (bucket_completed / bucket_total * 100.0) if bucket_total else 0.0
            bucket_overdue_rate = (bucket_overdue / bucket_total * 100.0) if bucket_total else 0.0

            trending = bucket_total >= MIN_SAMPLE_SIZE_FOR_FLAGGING and bucket_overdue_rate > threshold

            bu_summaries.append(
                BusinessUnitTrainingSummary(
                    business_unit_id=bu_id,
                    business_unit_name=bu_names.get(bu_id) if bu_id else "No business unit assigned",
                    total_assigned=bucket_total,
                    completed_count=bucket_completed,
                    completion_rate=round(bucket_completion_rate, 2),
                    overdue_count=bucket_overdue,
                    overdue_rate=round(bucket_overdue_rate, 2),
                    trending_toward_noncompliance=trending,
                    overdue_details=[
                        OverdueTrainingDetail(
                            record_id=r.id,
                            user_id=r.user_id,
                            training_type=r.training_type,
                            due_date=r.due_date,
                        )
                        for r in overdue_rows
                    ],
                )
            )

        return TrainingAnalyticsSummaryResponse(
            organization_id=org_id,
            total_assigned=total_assigned,
            total_completed=total_completed,
            overall_completion_rate=round(overall_completion_rate, 2),
            overall_overdue_count=overall_overdue_count,
            overall_overdue_rate=round(overall_overdue_rate, 2),
            trending_threshold_note=TRENDING_RULE_NOTE,
            business_units=bu_summaries,
            generated_at=now,
        )
