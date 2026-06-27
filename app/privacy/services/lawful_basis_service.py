import uuid
from datetime import UTC, date, datetime

from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.lawful_basis_record import LawfulBasisRecord
from app.models.processing_activity import ProcessingActivity
from app.services.audit_service import AuditService

ALLOWED_LAWFUL_BASIS = {
    "consent",
    "contract",
    "legal_obligation",
    "vital_interests",
    "public_task",
    "legitimate_interests",
}


class LawfulBasisService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _require_activity(self, org_id: uuid.UUID, activity_id: uuid.UUID) -> ProcessingActivity:
        row = self.db.execute(
            select(ProcessingActivity).where(
                ProcessingActivity.organization_id == org_id,
                ProcessingActivity.id == activity_id,
                ProcessingActivity.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Processing activity not found")
        return row

    def _require_record(self, org_id: uuid.UUID, record_id: uuid.UUID) -> LawfulBasisRecord:
        row = self.db.execute(
            select(LawfulBasisRecord).where(
                LawfulBasisRecord.organization_id == org_id,
                LawfulBasisRecord.id == record_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lawful basis record not found")
        return row

    def _validate_lia(self, lawful_basis: str, legitimate_interest_assessment: str | None) -> None:
        if lawful_basis not in ALLOWED_LAWFUL_BASIS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid lawful_basis")
        if lawful_basis == "legitimate_interests" and not legitimate_interest_assessment:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="legitimate_interest_assessment is required")

    def document_basis(self, org_id: uuid.UUID, activity_id: uuid.UUID, data, user_id: uuid.UUID) -> LawfulBasisRecord:
        self._require_activity(org_id, activity_id)
        payload = data.model_dump() if hasattr(data, "model_dump") else dict(data)

        lawful_basis = payload["lawful_basis"]
        lia = payload.get("legitimate_interest_assessment")
        self._validate_lia(lawful_basis, lia)

        existing = self.db.execute(
            select(LawfulBasisRecord).where(
                LawfulBasisRecord.organization_id == org_id,
                LawfulBasisRecord.processing_activity_id == activity_id,
                LawfulBasisRecord.lawful_basis == lawful_basis,
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Lawful basis already documented for activity")

        now = self.utcnow()
        row = LawfulBasisRecord(
            organization_id=org_id,
            processing_activity_id=activity_id,
            lawful_basis=lawful_basis,
            basis_description=payload["basis_description"],
            applicable_frameworks=payload.get("applicable_frameworks") or [],
            article_reference=payload.get("article_reference"),
            legitimate_interest_assessment=lia,
            review_required_at=payload.get("review_required_at"),
            is_active=True,
            documented_by=user_id,
            documented_at=now,
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="lawful_basis.documented",
            entity_type="lawful_basis_record",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"processing_activity_id": str(activity_id), "lawful_basis": row.lawful_basis},
            metadata_json={"source": "api"},
        )
        return row

    def get_basis_records(self, org_id: uuid.UUID, activity_id: uuid.UUID) -> list[LawfulBasisRecord]:
        self._require_activity(org_id, activity_id)
        return self.db.execute(
            select(LawfulBasisRecord)
            .where(
                LawfulBasisRecord.organization_id == org_id,
                LawfulBasisRecord.processing_activity_id == activity_id,
            )
            .order_by(LawfulBasisRecord.created_at.desc())
        ).scalars().all()

    def list_all_bases(
        self,
        org_id: uuid.UUID,
        lawful_basis: str | None = None,
        is_active: bool | None = None,
    ) -> list[LawfulBasisRecord]:
        stmt = select(LawfulBasisRecord).where(LawfulBasisRecord.organization_id == org_id)
        if lawful_basis is not None:
            if lawful_basis not in ALLOWED_LAWFUL_BASIS:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid lawful_basis filter")
            stmt = stmt.where(LawfulBasisRecord.lawful_basis == lawful_basis)
        if is_active is not None:
            stmt = stmt.where(LawfulBasisRecord.is_active.is_(is_active))
        return self.db.execute(stmt.order_by(LawfulBasisRecord.created_at.desc())).scalars().all()

    def update_basis(self, org_id: uuid.UUID, record_id: uuid.UUID, data, user_id: uuid.UUID) -> LawfulBasisRecord:
        row = self._require_record(org_id, record_id)
        payload = data.model_dump(exclude_unset=True)

        target_basis = payload.get("lawful_basis", row.lawful_basis)
        target_lia = payload.get("legitimate_interest_assessment", row.legitimate_interest_assessment)
        self._validate_lia(target_basis, target_lia)

        for key, value in payload.items():
            setattr(row, key, value)
        row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="lawful_basis.updated",
            entity_type="lawful_basis_record",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"lawful_basis": row.lawful_basis, "is_active": row.is_active},
            metadata_json={"source": "api"},
        )
        return row

    def deactivate_basis(self, org_id: uuid.UUID, record_id: uuid.UUID, user_id: uuid.UUID) -> LawfulBasisRecord:
        row = self._require_record(org_id, record_id)
        row.is_active = False
        row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="lawful_basis.deactivated",
            entity_type="lawful_basis_record",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"is_active": row.is_active},
            metadata_json={"source": "api"},
        )
        return row

    def get_basis_summary(self, org_id: uuid.UUID) -> dict:
        total_activities_with_basis = int(
            self.db.execute(
                select(func.count(func.distinct(LawfulBasisRecord.processing_activity_id))).where(
                    LawfulBasisRecord.organization_id == org_id,
                    LawfulBasisRecord.is_active.is_(True),
                )
            ).scalar_one()
            or 0
        )

        activities_without_basis = int(
            self.db.execute(
                select(func.count(ProcessingActivity.id)).where(
                    ProcessingActivity.organization_id == org_id,
                    ProcessingActivity.deleted_at.is_(None),
                    ~ProcessingActivity.id.in_(
                        select(LawfulBasisRecord.processing_activity_id).where(
                            LawfulBasisRecord.organization_id == org_id,
                            LawfulBasisRecord.is_active.is_(True),
                        )
                    ),
                )
            ).scalar_one()
            or 0
        )

        by_basis_rows = self.db.execute(
            select(LawfulBasisRecord.lawful_basis, func.count(LawfulBasisRecord.id))
            .where(
                LawfulBasisRecord.organization_id == org_id,
                LawfulBasisRecord.is_active.is_(True),
            )
            .group_by(LawfulBasisRecord.lawful_basis)
        ).all()
        by_lawful_basis = {str(k): int(v) for k, v in by_basis_rows}

        legitimate_interests_count = int(
            self.db.execute(
                select(func.count(LawfulBasisRecord.id)).where(
                    LawfulBasisRecord.organization_id == org_id,
                    LawfulBasisRecord.is_active.is_(True),
                    LawfulBasisRecord.lawful_basis == "legitimate_interests",
                )
            ).scalar_one()
            or 0
        )

        review_due_count = int(
            self.db.execute(
                select(func.count(LawfulBasisRecord.id)).where(
                    LawfulBasisRecord.organization_id == org_id,
                    LawfulBasisRecord.is_active.is_(True),
                    LawfulBasisRecord.review_required_at.is_not(None),
                    LawfulBasisRecord.review_required_at < date.today(),
                )
            ).scalar_one()
            or 0
        )

        return {
            "total_activities_with_basis": total_activities_with_basis,
            "activities_without_basis": activities_without_basis,
            "by_lawful_basis": by_lawful_basis,
            "legitimate_interests_count": legitimate_interests_count,
            "review_due_count": review_due_count,
        }
    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)
