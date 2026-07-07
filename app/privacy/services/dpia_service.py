import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import case, func, select
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

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _has_text(value: str | None) -> bool:
        return bool((value or "").strip())

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

    def _checklist_stats_map(self, org_id: uuid.UUID, dpia_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
        if not dpia_ids:
            return {}
        rows = self.db.execute(
            select(
                DPIAChecklistItem.dpia_id,
                func.count(DPIAChecklistItem.id),
                func.coalesce(
                    func.sum(
                        case(
                            (DPIAChecklistItem.response.is_not(None), 1),
                            else_=0,
                        )
                    ),
                    0,
                ),
            )
            .where(
                DPIAChecklistItem.organization_id == org_id,
                DPIAChecklistItem.dpia_id.in_(dpia_ids),
            )
            .group_by(DPIAChecklistItem.dpia_id)
        ).all()
        return {dpia_id: (int(total), int(answered)) for dpia_id, total, answered in rows}

    def _checklist_map(self, org_id: uuid.UUID, dpia_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[DPIAChecklistItem]]:
        if not dpia_ids:
            return {}
        rows = self.db.execute(
            select(DPIAChecklistItem)
            .where(
                DPIAChecklistItem.organization_id == org_id,
                DPIAChecklistItem.dpia_id.in_(dpia_ids),
            )
            .order_by(DPIAChecklistItem.order_index.asc())
        ).scalars().all()
        grouped: dict[uuid.UUID, list[DPIAChecklistItem]] = {dpia_id: [] for dpia_id in dpia_ids}
        for row in rows:
            grouped.setdefault(row.dpia_id, []).append(row)
        return grouped

    def _activity_map(self, org_id: uuid.UUID, activity_ids: list[uuid.UUID]) -> dict[uuid.UUID, ProcessingActivity]:
        if not activity_ids:
            return {}
        rows = self.db.execute(
            select(ProcessingActivity).where(
                ProcessingActivity.organization_id == org_id,
                ProcessingActivity.id.in_(activity_ids),
                ProcessingActivity.deleted_at.is_(None),
            )
        ).scalars()
        return {row.id: row for row in rows}

    def dpia_context(
        self,
        row: DPIA,
        *,
        checklist_items: list[DPIAChecklistItem] | None = None,
        checklist_stats: tuple[int, int] | None = None,
        activity: ProcessingActivity | None = None,
        now: datetime | None = None,
    ) -> dict:
        evaluated_now = now or self.utcnow()
        created_at = self._as_utc(row.created_at) or evaluated_now
        updated_at = self._as_utc(row.updated_at) or evaluated_now
        age_days = max(0, int((evaluated_now - created_at).total_seconds() // 86400))

        if checklist_items is not None:
            total_checklist_items = len(checklist_items)
            answered_checklist_items = sum(1 for item in checklist_items if item.response is not None)
        elif checklist_stats is not None:
            total_checklist_items, answered_checklist_items = checklist_stats
        else:
            stats = self._checklist_stats_map(row.organization_id, [row.id]).get(row.id, (0, 0))
            total_checklist_items, answered_checklist_items = stats

        checklist_completion_rate = (
            round((answered_checklist_items / total_checklist_items) * 100, 2) if total_checklist_items > 0 else 0.0
        )

        pending_review_days = 0
        if row.status == "under_review":
            pending_review_days = max(0, int((evaluated_now - updated_at).total_seconds() // 86400))

        linked_activity = activity
        if linked_activity is None:
            linked_activity = self.db.execute(
                select(ProcessingActivity).where(
                    ProcessingActivity.organization_id == row.organization_id,
                    ProcessingActivity.id == row.processing_activity_id,
                    ProcessingActivity.deleted_at.is_(None),
                )
            ).scalar_one_or_none()

        context_flags: list[str] = []
        if total_checklist_items > 0 and answered_checklist_items < total_checklist_items:
            context_flags.append("checklist_incomplete")
        if row.status == "under_review":
            if row.assigned_reviewer_id is None:
                context_flags.append("reviewer_unassigned")
            if pending_review_days >= 7:
                context_flags.append("review_overdue")
        if row.residual_risk_level in {"high", "unacceptable"}:
            context_flags.append("high_residual_risk")
            if not row.dpo_consulted:
                context_flags.append("dpo_consultation_missing")
        if row.residual_risk_level == "unacceptable" and not row.supervisory_authority_consulted:
            context_flags.append("sa_consultation_required")
        if row.supervisory_authority_consulted and not self._has_text(row.sa_consultation_notes):
            context_flags.append("sa_consultation_notes_missing")
        if row.dpo_consulted and not self._has_text(row.dpo_opinion):
            context_flags.append("dpo_opinion_missing")
        if row.risks_identified and not row.mitigation_measures:
            context_flags.append("mitigation_missing_for_identified_risks")
        if row.next_review_date is not None and row.next_review_date < evaluated_now.date():
            context_flags.append("next_review_overdue")
        if linked_activity is not None and row.status == "approved" and row.approved_at is not None:
            approved_at = self._as_utc(row.approved_at) or evaluated_now
            activity_updated_at = self._as_utc(linked_activity.updated_at) or approved_at
            if activity_updated_at > approved_at:
                context_flags.append("activity_changed_since_approval")

        return {
            "total_checklist_items": total_checklist_items,
            "answered_checklist_items": answered_checklist_items,
            "checklist_completion_rate": checklist_completion_rate,
            "pending_review_days": pending_review_days,
            "age_days": age_days,
            "context_flags": context_flags,
        }

    def dpia_response_payload(
        self,
        row: DPIA,
        *,
        checklist_items: list[DPIAChecklistItem] | None = None,
        checklist_stats: tuple[int, int] | None = None,
        activity: ProcessingActivity | None = None,
    ) -> dict:
        items = checklist_items if checklist_items is not None else self._list_checklist(row.organization_id, row.id)
        context = self.dpia_context(
            row,
            checklist_items=items,
            checklist_stats=checklist_stats,
            activity=activity,
        )
        return {
            "id": row.id,
            "organization_id": row.organization_id,
            "processing_activity_id": row.processing_activity_id,
            "title": row.title,
            "status": row.status,
            "nature_of_processing": row.nature_of_processing,
            "necessity_assessment": row.necessity_assessment,
            "proportionality_assessment": row.proportionality_assessment,
            "risks_identified": row.risks_identified,
            "risk_assessment_notes": row.risk_assessment_notes,
            "mitigation_measures": row.mitigation_measures,
            "residual_risk_level": row.residual_risk_level,
            "dpo_consulted": row.dpo_consulted,
            "dpo_opinion": row.dpo_opinion,
            "supervisory_authority_consulted": row.supervisory_authority_consulted,
            "sa_consultation_notes": row.sa_consultation_notes,
            "assigned_reviewer_id": row.assigned_reviewer_id,
            "reviewed_at": row.reviewed_at,
            "review_notes": row.review_notes,
            "approved_by": row.approved_by,
            "approved_at": row.approved_at,
            "next_review_date": row.next_review_date,
            "created_by": row.created_by,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "deleted_at": row.deleted_at,
            "checklist_items": items,
            "total_checklist_items": context["total_checklist_items"],
            "answered_checklist_items": context["answered_checklist_items"],
            "checklist_completion_rate": context["checklist_completion_rate"],
            "pending_review_days": context["pending_review_days"],
            "age_days": context["age_days"],
            "context_flags": context["context_flags"],
        }

    def dpia_response_payloads(self, org_id: uuid.UUID, rows: list[DPIA]) -> list[dict]:
        if not rows:
            return []
        dpia_ids = [row.id for row in rows]
        checklist_map = self._checklist_map(org_id, dpia_ids)
        checklist_stats_map = self._checklist_stats_map(org_id, dpia_ids)
        activity_map = self._activity_map(org_id, [row.processing_activity_id for row in rows])
        return [
            self.dpia_response_payload(
                row,
                checklist_items=checklist_map.get(row.id, []),
                checklist_stats=checklist_stats_map.get(row.id, (0, 0)),
                activity=activity_map.get(row.processing_activity_id),
            )
            for row in rows
        ]

    @staticmethod
    def _normalize_consultation_fields(payload: dict, existing: DPIA | None = None) -> None:
        dpo_consulted = payload.get("dpo_consulted", existing.dpo_consulted if existing is not None else False)
        if not dpo_consulted:
            payload["dpo_opinion"] = None
        supervisory_authority_consulted = payload.get(
            "supervisory_authority_consulted",
            existing.supervisory_authority_consulted if existing is not None else False,
        )
        if not supervisory_authority_consulted:
            payload["sa_consultation_notes"] = None

    def create_dpia(self, org_id: uuid.UUID, processing_activity_id: uuid.UUID, data, created_by: uuid.UUID) -> DPIA:
        self._require_activity(org_id, processing_activity_id)
        payload = data.model_dump() if hasattr(data, "model_dump") else dict(data)
        self._normalize_consultation_fields(payload)
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
        self._normalize_consultation_fields(payload, existing=row)
        if "status" in payload and payload["status"] not in ALLOWED_DPIA_STATUS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid status")
        if "residual_risk_level" in payload and payload["residual_risk_level"] is not None and payload["residual_risk_level"] not in ALLOWED_RESIDUAL_RISK:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid residual_risk_level")

        before_status = row.status
        before_risk = row.residual_risk_level

        for key, value in payload.items():
            setattr(row, key, value)
        row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="dpia.updated",
            entity_type="dpia",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            before_json={"status": before_status, "residual_risk_level": before_risk},
            after_json={"status": row.status, "residual_risk_level": row.residual_risk_level},
            metadata_json={"source": "api", "updated_fields": sorted(payload.keys())},
        )

        return row

    def respond_checklist(self, org_id: uuid.UUID, dpia_id: uuid.UUID, responses: list[dict], user_id: uuid.UUID) -> DPIA:
        row = self._require_dpia(org_id, dpia_id)
        now = self.utcnow()
        seen_keys: set[str] = set()

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
            if key in seen_keys:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Duplicate checklist criterion in payload: {key}",
                )
            seen_keys.add(key)
            item = items_by_key.get(key)
            if item is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Checklist criterion not found: {key}")
            value = response.get("response")
            value = validate_choice(value, ALLOWED_CHECKLIST_RESPONSE, "checklist response")
            notes = response.get("notes")
            if value in {"no", "partial"} and not self._has_text(notes):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Checklist notes are required for response={value} on criterion={key}",
                )
            item.response = value
            item.notes = notes
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
        if row.assigned_reviewer_id is not None and row.assigned_reviewer_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Only the assigned reviewer can approve this DPIA",
            )

        checklist = self._list_checklist(org_id, row.id)
        if any(item.response is None for item in checklist):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="All checklist items must be answered before approval")
        if row.residual_risk_level in {"high", "unacceptable"} and not row.dpo_consulted:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="dpo_consulted must be true before approving high or unacceptable residual risk",
            )
        if row.dpo_consulted and not self._has_text(row.dpo_opinion):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="dpo_opinion is required when dpo_consulted is true",
            )
        if row.residual_risk_level == "unacceptable" and not row.supervisory_authority_consulted:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="supervisory_authority_consulted must be true for unacceptable residual risk",
            )
        if row.supervisory_authority_consulted and not self._has_text(row.sa_consultation_notes):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="sa_consultation_notes are required when supervisory_authority_consulted is true",
            )

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
        under_review_count = int(
            self.db.execute(select(func.count(DPIA.id)).where(*base_filters, DPIA.status == "under_review")).scalar_one() or 0
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

        now = self.utcnow()
        overdue_review_count = int(
            self.db.execute(
                select(func.count(DPIA.id)).where(
                    *base_filters,
                    DPIA.status == "under_review",
                    DPIA.updated_at < (now - timedelta(days=7)),
                )
            ).scalar_one()
            or 0
        )

        all_rows = self.db.execute(select(DPIA).where(*base_filters)).scalars().all()
        checklist_stats = self._checklist_stats_map(org_id, [row.id for row in all_rows])
        activity_map = self._activity_map(org_id, [row.processing_activity_id for row in all_rows])

        approval_blocked_count = 0
        approved_stale_activity_count = 0
        for row in all_rows:
            context = self.dpia_context(
                row,
                checklist_stats=checklist_stats.get(row.id, (0, 0)),
                activity=activity_map.get(row.processing_activity_id),
                now=now,
            )
            if row.status == "under_review" and any(
                flag in context["context_flags"]
                for flag in {
                    "checklist_incomplete",
                    "dpo_consultation_missing",
                    "dpo_opinion_missing",
                    "sa_consultation_required",
                    "sa_consultation_notes_missing",
                }
            ):
                approval_blocked_count += 1
            if row.status == "approved" and "activity_changed_since_approval" in context["context_flags"]:
                approved_stale_activity_count += 1

        context_flags: list[str] = []
        if required_but_missing > 0:
            context_flags.append("activities_require_dpia_missing_assessment")
        if approval_blocked_count > 0:
            context_flags.append("under_review_approvals_blocked")
        if overdue_review_count > 0:
            context_flags.append("review_cycle_slowdown")
        if approved_stale_activity_count > 0:
            context_flags.append("approved_dpias_potentially_stale")

        return {
            "total": total,
            "by_status": by_status,
            "by_residual_risk": by_residual_risk,
            "approved_count": approved_count,
            "required_but_missing": required_but_missing,
            "under_review_count": under_review_count,
            "overdue_review_count": overdue_review_count,
            "approval_blocked_count": approval_blocked_count,
            "approved_stale_activity_count": approved_stale_activity_count,
            "context_flags": context_flags,
        }

    def soft_delete_dpia(self, org_id: uuid.UUID, dpia_id: uuid.UUID, user_id: uuid.UUID) -> None:
        row = self._require_dpia(org_id, dpia_id)
        if row.status not in {"draft", "rejected"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="DPIA can only be deleted from draft or rejected status")

        now = self.utcnow()
        activity = self.db.execute(
            select(ProcessingActivity).where(
                ProcessingActivity.organization_id == org_id,
                ProcessingActivity.id == row.processing_activity_id,
                ProcessingActivity.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        unlinked_activity = False
        if activity is not None and activity.linked_dpia_id == row.id:
            activity.linked_dpia_id = None
            activity.updated_at = now
            unlinked_activity = True

        row.deleted_at = now
        row.updated_at = now
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="dpia.deleted",
            entity_type="dpia",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"deleted_at": now.isoformat(), "processing_activity_unlinked": unlinked_activity},
            metadata_json={"source": "api"},
        )
