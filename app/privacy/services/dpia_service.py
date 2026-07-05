import uuid
from datetime import UTC, date, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.dpia import DPIA
from app.models.dpia_checklist_item import DPIAChecklistItem
from app.models.membership import Membership
from app.models.processing_activity import ProcessingActivity
from app.models.user import User
from app.services.audit_service import AuditService
from app.core.validation import validate_choice

ALLOWED_DPIA_STATUS = {"draft", "in_progress", "under_review", "approved", "rejected", "archived"}
ALLOWED_RESIDUAL_RISK = {"low", "medium", "high", "unacceptable"}
ALLOWED_CHECKLIST_RESPONSE = {"yes", "no", "partial", "na"}

DPIA_CHECKLIST: dict[str, str] = {
    "systematic_description": (
        "Has a systematic description of the processing been prepared (Art. 35(7)(a))?"
    ),
    "necessity_proportionality": (
        "Has the necessity and proportionality of the processing been assessed (Art. 35(7)(b))?"
    ),
    "risk_assessment": (
        "Have risks to the rights and freedoms of data subjects been assessed (Art. 35(7)(c))?"
    ),
    "measures_identified": (
        "Have measures to address the risks been identified (Art. 35(7)(d))?"
    ),
    "data_minimization": "Has data minimization been applied?",
    "security_measures": (
        "Have appropriate technical and organizational security measures been defined?"
    ),
    "retention_limits": "Are data retention limits defined and enforced?",
    "data_subject_rights": (
        "Have data subject rights mechanisms been implemented for this processing activity?"
    ),
    "dpo_reviewed": "Has the Data Protection Officer reviewed this assessment?",
    "sa_prior_consultation": (
        "Has prior consultation with the supervisory authority been conducted if residual risk is unacceptable?"
    ),
}


class DPIAService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

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

    def _require_dpia(self, org_id: uuid.UUID, dpia_id: uuid.UUID) -> DPIA:
        row = self.db.execute(
            select(DPIA).where(
                DPIA.organization_id == org_id,
                DPIA.id == dpia_id,
                DPIA.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DPIA not found")
        return row

    def _require_active_org_user(self, org_id: uuid.UUID, user_id: uuid.UUID, field_name: str) -> None:
        row = self.db.execute(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(
                User.id == user_id,
                User.is_active.is_(True),
                User.status == "active",
                Membership.organization_id == org_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{field_name} must be an active organization user",
            )

    def _list_checklist(self, org_id: uuid.UUID, dpia_id: uuid.UUID) -> list[DPIAChecklistItem]:
        return self.db.execute(
            select(DPIAChecklistItem)
            .where(
                DPIAChecklistItem.organization_id == org_id,
                DPIAChecklistItem.dpia_id == dpia_id,
            )
            .order_by(DPIAChecklistItem.order_index.asc())
        ).scalars().all()

    def create_dpia(self, org_id: uuid.UUID, processing_activity_id: uuid.UUID, data, created_by: uuid.UUID) -> DPIA:
        self._require_activity(org_id, processing_activity_id)
        payload = data.model_dump() if hasattr(data, "model_dump") else dict(data)
        if payload.get("residual_risk_level") and payload["residual_risk_level"] not in ALLOWED_RESIDUAL_RISK:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid residual_risk_level")

        now = self.utcnow()
        row = DPIA(
            organization_id=org_id,
            processing_activity_id=processing_activity_id,
            title=payload["title"],
            status="draft",
            nature_of_processing=payload.get("nature_of_processing"),
            necessity_assessment=payload.get("necessity_assessment"),
            proportionality_assessment=payload.get("proportionality_assessment"),
            risks_identified=payload.get("risks_identified") or [],
            risk_assessment_notes=payload.get("risk_assessment_notes"),
            mitigation_measures=payload.get("mitigation_measures") or [],
            residual_risk_level=payload.get("residual_risk_level"),
            dpo_consulted=bool(payload.get("dpo_consulted", False)),
            dpo_opinion=payload.get("dpo_opinion"),
            supervisory_authority_consulted=bool(payload.get("supervisory_authority_consulted", False)),
            sa_consultation_notes=payload.get("sa_consultation_notes"),
            assigned_reviewer_id=None,
            reviewed_at=None,
            review_notes=None,
            approved_by=None,
            approved_at=None,
            next_review_date=payload.get("next_review_date"),
            created_by=created_by,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
        self.db.add(row)
        self.db.flush()

        for idx, (criterion_key, question) in enumerate(DPIA_CHECKLIST.items(), start=1):
            item = DPIAChecklistItem(
                organization_id=org_id,
                dpia_id=row.id,
                criterion_key=criterion_key,
                question=question,
                response=None,
                notes=None,
                order_index=idx,
                created_at=now,
                updated_at=now,
            )
            self.db.add(item)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="dpia.created",
            entity_type="dpia",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={"processing_activity_id": str(processing_activity_id), "status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def get_dpia(self, org_id: uuid.UUID, dpia_id: uuid.UUID) -> DPIA:
        row = self._require_dpia(org_id, dpia_id)
        row.checklist_items = self._list_checklist(org_id, dpia_id)  # type: ignore[attr-defined]
        return row

    def list_dpias(
        self,
        org_id: uuid.UUID,
        status_filter: str | None = None,
        processing_activity_id: uuid.UUID | None = None,
        residual_risk_level: str | None = None,
    ) -> list[DPIA]:
        stmt = select(DPIA).where(
            DPIA.organization_id == org_id,
            DPIA.deleted_at.is_(None),
        )
        if status_filter is not None:
            status_filter = validate_choice(status_filter, ALLOWED_DPIA_STATUS, "status")
            stmt = stmt.where(DPIA.status == status_filter)
        if processing_activity_id is not None:
            stmt = stmt.where(DPIA.processing_activity_id == processing_activity_id)
        if residual_risk_level is not None:
            residual_risk_level = validate_choice(residual_risk_level, ALLOWED_RESIDUAL_RISK, "residual_risk_level")
            stmt = stmt.where(DPIA.residual_risk_level == residual_risk_level)

        return self.db.execute(stmt.order_by(DPIA.created_at.desc())).scalars().all()

    def update_dpia(self, org_id: uuid.UUID, dpia_id: uuid.UUID, data, actor_user_id: uuid.UUID) -> DPIA:
        row = self._require_dpia(org_id, dpia_id)
        if row.status == "approved":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Approved DPIA cannot be updated")

        payload = data.model_dump(exclude_unset=True)
        if "status" in payload and payload["status"] not in ALLOWED_DPIA_STATUS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid status")
        if "residual_risk_level" in payload and payload["residual_risk_level"] is not None and payload["residual_risk_level"] not in ALLOWED_RESIDUAL_RISK:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid residual_risk_level")

        for key, value in payload.items():
            setattr(row, key, value)
        row.updated_at = self.utcnow()
        self.db.flush()

        return row

    def respond_checklist(self, org_id: uuid.UUID, dpia_id: uuid.UUID, responses: list[dict], user_id: uuid.UUID) -> DPIA:
        row = self._require_dpia(org_id, dpia_id)
        now = self.utcnow()

        items_by_key = {
            item.criterion_key: item
            for item in self.db.execute(
                select(DPIAChecklistItem).where(
                    DPIAChecklistItem.organization_id == org_id,
                    DPIAChecklistItem.dpia_id == dpia_id,
                )
            ).scalars().all()
        }

        for response in responses:
            key = response.get("criterion_key")
            item = items_by_key.get(key)
            if item is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Checklist criterion not found: {key}")
            value = response.get("response")
            value = validate_choice(value, ALLOWED_CHECKLIST_RESPONSE, "checklist response")
            item.response = value
            item.notes = response.get("notes")
            item.updated_at = now

        if row.status == "draft":
            row.status = "in_progress"
        row.updated_at = now
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="dpia.checklist_responded",
            entity_type="dpia",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"responses_count": len(responses), "status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def submit_for_review(self, org_id: uuid.UUID, dpia_id: uuid.UUID, reviewer_id: uuid.UUID, user_id: uuid.UUID) -> DPIA:
        row = self._require_dpia(org_id, dpia_id)
        if row.status not in {"draft", "in_progress", "rejected"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="DPIA cannot be submitted for review from current status")
        self._require_active_org_user(org_id, reviewer_id, "reviewer_id")

        now = self.utcnow()
        row.status = "under_review"
        row.assigned_reviewer_id = reviewer_id
        row.reviewed_at = None
        row.updated_at = now
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="dpia.submitted_for_review",
            entity_type="dpia",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"assigned_reviewer_id": str(reviewer_id), "status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def approve_dpia(self, org_id: uuid.UUID, dpia_id: uuid.UUID, user_id: uuid.UUID, notes: str | None = None) -> DPIA:
        row = self._require_dpia(org_id, dpia_id)
        if row.status != "under_review":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only under_review DPIA can be approved")
        if row.created_by == user_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Four-eyes rule violation")

        checklist = self._list_checklist(org_id, row.id)
        if any(item.response is None for item in checklist):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="All checklist items must be answered before approval")

        activity = self._require_activity(org_id, row.processing_activity_id)

        now = self.utcnow()
        row.status = "approved"
        row.approved_by = user_id
        row.approved_at = now
        row.review_notes = notes
        row.reviewed_at = now
        row.updated_at = now

        activity.linked_dpia_id = row.id
        activity.updated_at = now

        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="dpia.approved",
            entity_type="dpia",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status, "processing_activity_id": str(activity.id)},
            metadata_json={"source": "api"},
        )
        return row

    def reject_dpia(self, org_id: uuid.UUID, dpia_id: uuid.UUID, user_id: uuid.UUID, notes: str) -> DPIA:
        row = self._require_dpia(org_id, dpia_id)
        if row.status != "under_review":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only under_review DPIA can be rejected")
        if not notes:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Rejection notes are required")

        now = self.utcnow()
        row.status = "rejected"
        row.review_notes = notes
        row.reviewed_at = now
        row.updated_at = now
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="dpia.rejected",
            entity_type="dpia",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status, "review_notes": notes},
            metadata_json={"source": "api"},
        )
        return row

    def get_dpia_summary(self, org_id: uuid.UUID) -> dict:
        base_filters = [DPIA.organization_id == org_id, DPIA.deleted_at.is_(None)]

        total = int(self.db.execute(select(func.count(DPIA.id)).where(*base_filters)).scalar_one() or 0)

        by_status_rows = self.db.execute(
            select(DPIA.status, func.count(DPIA.id)).where(*base_filters).group_by(DPIA.status)
        ).all()
        by_status = {str(key): int(value) for key, value in by_status_rows}

        by_risk_rows = self.db.execute(
            select(DPIA.residual_risk_level, func.count(DPIA.id))
            .where(*base_filters, DPIA.residual_risk_level.is_not(None))
            .group_by(DPIA.residual_risk_level)
        ).all()
        by_residual_risk = {str(key): int(value) for key, value in by_risk_rows}

        approved_count = int(
            self.db.execute(select(func.count(DPIA.id)).where(*base_filters, DPIA.status == "approved")).scalar_one() or 0
        )

        required_but_missing = int(
            self.db.execute(
                select(func.count(ProcessingActivity.id)).where(
                    ProcessingActivity.organization_id == org_id,
                    ProcessingActivity.deleted_at.is_(None),
                    ProcessingActivity.requires_dpia.is_(True),
                    ProcessingActivity.linked_dpia_id.is_(None),
                )
            ).scalar_one()
            or 0
        )

        return {
            "total": total,
            "by_status": by_status,
            "by_residual_risk": by_residual_risk,
            "approved_count": approved_count,
            "required_but_missing": required_but_missing,
        }

    def soft_delete_dpia(self, org_id: uuid.UUID, dpia_id: uuid.UUID, user_id: uuid.UUID) -> None:
        row = self._require_dpia(org_id, dpia_id)
        if row.status not in {"draft", "rejected"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="DPIA can only be deleted from draft or rejected status")

        now = self.utcnow()
        row.deleted_at = now
        row.updated_at = now
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="dpia.deleted",
            entity_type="dpia",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"deleted_at": now.isoformat()},
            metadata_json={"source": "api"},
        )
