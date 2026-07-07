import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.data_asset import DataAsset
from app.models.dpia import DPIA
from app.models.framework import Framework
from app.models.membership import Membership
from app.models.obligation import Obligation
from app.models.processing_activity import ProcessingActivity
from app.models.ropa_framework_link import RopaFrameworkLink
from app.models.subprocessor import Subprocessor
from app.models.user import User
from app.services.audit_service import AuditService
from app.core.validation import validate_choice

ALLOWED_LEGAL_BASIS = {
    "consent",
    "contract",
    "legal_obligation",
    "vital_interests",
    "public_task",
    "legitimate_interests",
}
ALLOWED_STATUS = {"active", "under_review", "suspended", "discontinued"}
ALLOWED_RISK_LEVEL = {"low", "medium", "high", "critical"}


class RopaService:
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

    def _validate_transfer_consistency(
        self,
        *,
        international_transfers: bool,
        transfer_destinations: list | None,
        transfer_safeguards: str | None,
    ) -> tuple[list, str | None]:
        normalized_destinations = transfer_destinations or []
        normalized_safeguards = transfer_safeguards
        if not international_transfers:
            # Keep persisted shape consistent when transfers are disabled.
            normalized_destinations = []
            normalized_safeguards = None
        return normalized_destinations, normalized_safeguards

    @staticmethod
    def _validate_legal_basis_dependencies(*, legal_basis: str, legitimate_interest_justification: str | None) -> None:
        if legal_basis == "legitimate_interests" and not (legitimate_interest_justification or "").strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="legitimate_interest_justification is required for legal_basis=legitimate_interests",
            )

    def activity_context(self, row: ProcessingActivity, *, now: datetime | None = None) -> dict:
        evaluated_now = now or self.utcnow()
        updated_at = self._as_utc(row.updated_at) or evaluated_now
        age_days = max(0, int((evaluated_now - updated_at).total_seconds() // 86400))
        linkage_count = len(row.linked_data_asset_ids or []) + len(row.linked_subprocessor_ids or [])
        if row.linked_dpia_id is not None:
            linkage_count += 1

        context_flags: list[str] = []
        if row.requires_dpia and row.linked_dpia_id is None:
            context_flags.append("requires_dpia_missing_linked_dpia")
        if row.international_transfers and not (row.transfer_destinations or []):
            context_flags.append("transfer_destinations_missing")
        if row.legal_basis == "legitimate_interests" and not (row.legitimate_interest_justification or "").strip():
            context_flags.append("legitimate_interest_justification_missing")
        if age_days >= 180 and row.status in {"active", "under_review"}:
            context_flags.append("activity_stale_for_review")
        if not (row.retention_period or "").strip():
            context_flags.append("retention_period_missing")

        return {"age_days": age_days, "linkage_count": linkage_count, "context_flags": context_flags}

    def activity_response_payload(self, row: ProcessingActivity) -> dict:
        context = self.activity_context(row)
        return {
            "id": row.id,
            "organization_id": row.organization_id,
            "name": row.name,
            "description": row.description,
            "purpose": row.purpose,
            "legal_basis": row.legal_basis,
            "legitimate_interest_justification": row.legitimate_interest_justification,
            "data_categories": row.data_categories,
            "special_categories": row.special_categories,
            "data_subject_types": row.data_subject_types,
            "retention_period": row.retention_period,
            "retention_basis": row.retention_basis,
            "recipients": row.recipients,
            "international_transfers": row.international_transfers,
            "transfer_destinations": row.transfer_destinations,
            "transfer_safeguards": row.transfer_safeguards,
            "controller_name": row.controller_name,
            "controller_contact": row.controller_contact,
            "dpo_contact": row.dpo_contact,
            "status": row.status,
            "risk_level": row.risk_level,
            "requires_dpia": row.requires_dpia,
            "linked_dpia_id": row.linked_dpia_id,
            "linked_data_asset_ids": row.linked_data_asset_ids,
            "linked_subprocessor_ids": row.linked_subprocessor_ids,
            "owner_id": row.owner_id,
            "created_by": row.created_by,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "deleted_at": row.deleted_at,
            "age_days": context["age_days"],
            "linkage_count": context["linkage_count"],
            "context_flags": context["context_flags"],
        }

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

    def _require_obligation(self, obligation_id: uuid.UUID) -> Obligation:
        row = self.db.execute(select(Obligation).where(Obligation.id == obligation_id)).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obligation not found")
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

    @staticmethod
    def _normalize_uuid_list(values: list | None, field_name: str) -> list[str]:
        normalized: list[str] = []
        for item in values or []:
            try:
                parsed = uuid.UUID(str(item))
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"{field_name} contains an invalid UUID",
                ) from exc
            text = str(parsed)
            if text not in normalized:
                normalized.append(text)
        return normalized

    def _validate_linked_dpia(self, org_id: uuid.UUID, dpia_id: uuid.UUID | None) -> None:
        if dpia_id is None:
            return
        row = self.db.execute(
            select(DPIA.id).where(
                DPIA.organization_id == org_id,
                DPIA.id == dpia_id,
                DPIA.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="linked_dpia_id must reference an organization DPIA",
            )

    def _normalize_data_asset_ids(self, org_id: uuid.UUID, values: list | None) -> list[str]:
        normalized = self._normalize_uuid_list(values, "linked_data_asset_ids")
        if not normalized:
            return []
        found = {
            str(row)
            for row in self.db.execute(
                select(DataAsset.id).where(
                    DataAsset.organization_id == org_id,
                    DataAsset.id.in_([uuid.UUID(item) for item in normalized]),
                    DataAsset.deleted_at.is_(None),
                )
            ).scalars()
        }
        missing = [item for item in normalized if item not in found]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="linked_data_asset_ids must reference organization data assets",
            )
        return normalized

    def _normalize_subprocessor_ids(self, org_id: uuid.UUID, values: list | None) -> list[str]:
        normalized = self._normalize_uuid_list(values, "linked_subprocessor_ids")
        if not normalized:
            return []
        found = {
            str(row)
            for row in self.db.execute(
                select(Subprocessor.id).where(
                    Subprocessor.organization_id == org_id,
                    Subprocessor.id.in_([uuid.UUID(item) for item in normalized]),
                    Subprocessor.deleted_at.is_(None),
                )
            ).scalars()
        }
        missing = [item for item in normalized if item not in found]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="linked_subprocessor_ids must reference organization subprocessors",
            )
        return normalized

    @staticmethod
    def _apply_requires_dpia_logic(
        *,
        special_categories: list,
        risk_level: str | None,
        current: bool,
        requested: bool | None,
    ) -> bool:
        if special_categories or risk_level in {"high", "critical"}:
            return True
        if requested is not None:
            return bool(requested)
        return current

    def create_activity(self, org_id: uuid.UUID, data, created_by: uuid.UUID) -> ProcessingActivity:
        payload = data.model_dump()
        payload["legal_basis"] = validate_choice(payload["legal_basis"], ALLOWED_LEGAL_BASIS, "legal_basis")
        if payload.get("status", "active") not in ALLOWED_STATUS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid status")
        if payload.get("risk_level") is not None and payload["risk_level"] not in ALLOWED_RISK_LEVEL:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid risk_level")
        self._require_active_org_user(org_id, payload["owner_id"], "owner_id")
        self._validate_legal_basis_dependencies(
            legal_basis=payload["legal_basis"],
            legitimate_interest_justification=payload.get("legitimate_interest_justification"),
        )
        payload["transfer_destinations"], payload["transfer_safeguards"] = self._validate_transfer_consistency(
            international_transfers=bool(payload.get("international_transfers", False)),
            transfer_destinations=payload.get("transfer_destinations"),
            transfer_safeguards=payload.get("transfer_safeguards"),
        )
        self._validate_linked_dpia(org_id, payload.get("linked_dpia_id"))
        payload["linked_data_asset_ids"] = self._normalize_data_asset_ids(org_id, payload.get("linked_data_asset_ids"))
        payload["linked_subprocessor_ids"] = self._normalize_subprocessor_ids(org_id, payload.get("linked_subprocessor_ids"))

        now = self.utcnow()
        requested_requires_dpia = payload.get("requires_dpia")
        row = ProcessingActivity(
            organization_id=org_id,
            name=payload["name"],
            description=payload.get("description"),
            purpose=payload["purpose"],
            legal_basis=payload["legal_basis"],
            legitimate_interest_justification=payload.get("legitimate_interest_justification"),
            data_categories=payload.get("data_categories") or [],
            special_categories=payload.get("special_categories") or [],
            data_subject_types=payload.get("data_subject_types") or [],
            retention_period=payload.get("retention_period"),
            retention_basis=payload.get("retention_basis"),
            recipients=payload.get("recipients") or [],
            international_transfers=bool(payload.get("international_transfers", False)),
            transfer_destinations=payload.get("transfer_destinations") or [],
            transfer_safeguards=payload.get("transfer_safeguards"),
            controller_name=payload.get("controller_name"),
            controller_contact=payload.get("controller_contact"),
            dpo_contact=payload.get("dpo_contact"),
            status=payload.get("status", "active"),
            risk_level=payload.get("risk_level"),
            requires_dpia=False,
            linked_dpia_id=payload.get("linked_dpia_id"),
            linked_data_asset_ids=payload.get("linked_data_asset_ids") or [],
            linked_subprocessor_ids=payload.get("linked_subprocessor_ids") or [],
            owner_id=payload["owner_id"],
            created_by=created_by,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
        row.requires_dpia = self._apply_requires_dpia_logic(
            special_categories=row.special_categories,
            risk_level=row.risk_level,
            current=False,
            requested=requested_requires_dpia,
        )

        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="ropa.activity_created",
            entity_type="processing_activity",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={"name": row.name, "legal_basis": row.legal_basis, "requires_dpia": row.requires_dpia},
            metadata_json={"source": "api"},
        )
        return row

    def get_activity(self, org_id: uuid.UUID, activity_id: uuid.UUID) -> ProcessingActivity:
        return self._require_activity(org_id, activity_id)

    def list_activities(
        self,
        org_id: uuid.UUID,
        status_filter: str | None = None,
        legal_basis: str | None = None,
        requires_dpia: bool | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ProcessingActivity]:
        stmt = select(ProcessingActivity).where(
            ProcessingActivity.organization_id == org_id,
            ProcessingActivity.deleted_at.is_(None),
        )
        if status_filter is not None:
            status_filter = validate_choice(status_filter, ALLOWED_STATUS, "status")
            stmt = stmt.where(ProcessingActivity.status == status_filter)
        if legal_basis is not None:
            legal_basis = validate_choice(legal_basis, ALLOWED_LEGAL_BASIS, "legal_basis")
            stmt = stmt.where(ProcessingActivity.legal_basis == legal_basis)
        if requires_dpia is not None:
            stmt = stmt.where(ProcessingActivity.requires_dpia.is_(requires_dpia))

        return self.db.execute(
            stmt.order_by(ProcessingActivity.created_at.desc()).offset(max(0, int(skip))).limit(max(1, min(int(limit), 500)))
        ).scalars().all()

    def update_activity(self, org_id: uuid.UUID, activity_id: uuid.UUID, data, actor_user_id: uuid.UUID | None = None) -> ProcessingActivity:
        row = self._require_activity(org_id, activity_id)
        payload = data.model_dump(exclude_unset=True)

        if "legal_basis" in payload and payload["legal_basis"] not in ALLOWED_LEGAL_BASIS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid legal_basis")
        if "status" in payload and payload["status"] not in ALLOWED_STATUS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid status")
        if "risk_level" in payload and payload["risk_level"] is not None and payload["risk_level"] not in ALLOWED_RISK_LEVEL:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid risk_level")
        if "owner_id" in payload and payload["owner_id"] is not None:
            self._require_active_org_user(org_id, payload["owner_id"], "owner_id")
        next_legal_basis = payload.get("legal_basis", row.legal_basis)
        next_legitimate_justification = payload.get("legitimate_interest_justification", row.legitimate_interest_justification)
        self._validate_legal_basis_dependencies(
            legal_basis=next_legal_basis,
            legitimate_interest_justification=next_legitimate_justification,
        )
        next_international_transfers = (
            payload["international_transfers"] if "international_transfers" in payload else row.international_transfers
        )
        next_transfer_destinations = payload.get("transfer_destinations", row.transfer_destinations)
        next_transfer_safeguards = payload.get("transfer_safeguards", row.transfer_safeguards)
        normalized_destinations, normalized_safeguards = self._validate_transfer_consistency(
            international_transfers=bool(next_international_transfers),
            transfer_destinations=next_transfer_destinations,
            transfer_safeguards=next_transfer_safeguards,
        )
        if "international_transfers" in payload or "transfer_destinations" in payload:
            payload["transfer_destinations"] = normalized_destinations
        if "international_transfers" in payload or "transfer_safeguards" in payload:
            payload["transfer_safeguards"] = normalized_safeguards
        if "linked_dpia_id" in payload:
            self._validate_linked_dpia(org_id, payload.get("linked_dpia_id"))
        if "linked_data_asset_ids" in payload:
            payload["linked_data_asset_ids"] = self._normalize_data_asset_ids(org_id, payload.get("linked_data_asset_ids"))
        if "linked_subprocessor_ids" in payload:
            payload["linked_subprocessor_ids"] = self._normalize_subprocessor_ids(org_id, payload.get("linked_subprocessor_ids"))

        for key, value in payload.items():
            setattr(row, key, value)

        row.requires_dpia = self._apply_requires_dpia_logic(
            special_categories=row.special_categories or [],
            risk_level=row.risk_level,
            current=row.requires_dpia,
            requested=payload.get("requires_dpia") if "requires_dpia" in payload else None,
        )
        row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="ropa.activity_updated",
            entity_type="processing_activity",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={"status": row.status, "risk_level": row.risk_level, "requires_dpia": row.requires_dpia},
            metadata_json={"source": "api"},
        )
        return row

    def link_obligation(
        self,
        org_id: uuid.UUID,
        activity_id: uuid.UUID,
        obligation_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> RopaFrameworkLink:
        self._require_activity(org_id, activity_id)
        self._require_obligation(obligation_id)

        existing = self.db.execute(
            select(RopaFrameworkLink).where(
                RopaFrameworkLink.organization_id == org_id,
                RopaFrameworkLink.processing_activity_id == activity_id,
                RopaFrameworkLink.obligation_id == obligation_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Obligation already linked")

        row = RopaFrameworkLink(
            organization_id=org_id,
            processing_activity_id=activity_id,
            obligation_id=obligation_id,
            linked_by=user_id,
            linked_at=self.utcnow(),
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="ropa.obligation_linked",
            entity_type="ropa_framework_link",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"processing_activity_id": str(activity_id), "obligation_id": str(obligation_id)},
            metadata_json={"source": "api"},
        )
        return row

    def unlink_obligation(self, org_id: uuid.UUID, activity_id: uuid.UUID, obligation_id: uuid.UUID, user_id: uuid.UUID) -> None:
        row = self.db.execute(
            select(RopaFrameworkLink).where(
                RopaFrameworkLink.organization_id == org_id,
                RopaFrameworkLink.processing_activity_id == activity_id,
                RopaFrameworkLink.obligation_id == obligation_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RoPA obligation link not found")

        self.db.delete(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="ropa.obligation_unlinked",
            entity_type="ropa_framework_link",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"processing_activity_id": str(activity_id), "obligation_id": str(obligation_id)},
            metadata_json={"source": "api"},
        )

    def get_activity_obligations(self, org_id: uuid.UUID, activity_id: uuid.UUID) -> list[dict]:
        self._require_activity(org_id, activity_id)
        rows = self.db.execute(
            select(RopaFrameworkLink, Obligation, Framework)
            .join(Obligation, Obligation.id == RopaFrameworkLink.obligation_id)
            .join(Framework, Framework.id == Obligation.framework_id)
            .where(
                RopaFrameworkLink.organization_id == org_id,
                RopaFrameworkLink.processing_activity_id == activity_id,
            )
            .order_by(Framework.name.asc(), Obligation.reference_code.asc())
        ).all()

        return [
            {
                "id": str(link.id),
                "organization_id": str(link.organization_id),
                "processing_activity_id": str(link.processing_activity_id),
                "obligation_id": str(link.obligation_id),
                "obligation_ref": obligation.reference_code,
                "obligation_title": obligation.title,
                "framework_name": framework.name,
                "linked_by": str(link.linked_by),
                "linked_at": link.linked_at,
            }
            for link, obligation, framework in rows
        ]

    def get_ropa_summary(self, org_id: uuid.UUID) -> dict:
        base_filters = [
            ProcessingActivity.organization_id == org_id,
            ProcessingActivity.deleted_at.is_(None),
        ]

        total_activities = int(self.db.execute(select(func.count(ProcessingActivity.id)).where(*base_filters)).scalar_one() or 0)
        status_rows = self.db.execute(
            select(ProcessingActivity.status, func.count(ProcessingActivity.id))
            .where(*base_filters)
            .group_by(ProcessingActivity.status)
        ).all()
        by_status = {str(k): int(v) for k, v in status_rows}

        basis_rows = self.db.execute(
            select(ProcessingActivity.legal_basis, func.count(ProcessingActivity.id))
            .where(*base_filters)
            .group_by(ProcessingActivity.legal_basis)
        ).all()
        by_legal_basis = {str(k): int(v) for k, v in basis_rows}

        requires_dpia_count = int(
            self.db.execute(select(func.count(ProcessingActivity.id)).where(*base_filters, ProcessingActivity.requires_dpia.is_(True))).scalar_one()
            or 0
        )
        with_international_transfers = int(
            self.db.execute(select(func.count(ProcessingActivity.id)).where(*base_filters, ProcessingActivity.international_transfers.is_(True))).scalar_one()
            or 0
        )
        rows_for_special_categories = self.db.execute(
            select(ProcessingActivity.special_categories).where(*base_filters)
        ).all()
        with_special_categories = sum(1 for (special_categories,) in rows_for_special_categories if special_categories)
        missing_dpia_count = int(
            self.db.execute(
                select(func.count(ProcessingActivity.id)).where(
                    *base_filters,
                    ProcessingActivity.requires_dpia.is_(True),
                    ProcessingActivity.linked_dpia_id.is_(None),
                )
            ).scalar_one()
            or 0
        )
        activity_rows = self.db.execute(select(ProcessingActivity).where(*base_filters)).scalars().all()
        stale_activity_count = sum(
            1
            for row in activity_rows
            if "activity_stale_for_review" in self.activity_context(row)["context_flags"]
        )
        high_risk_without_dpia_count = int(
            self.db.execute(
                select(func.count(ProcessingActivity.id)).where(
                    *base_filters,
                    ProcessingActivity.risk_level.in_(["high", "critical"]),
                    ProcessingActivity.linked_dpia_id.is_(None),
                )
            ).scalar_one()
            or 0
        )
        context_flags: list[str] = []
        if missing_dpia_count > 0:
            context_flags.append("requires_dpia_missing_links_present")
        if stale_activity_count > 0:
            context_flags.append("stale_activities_present")
        if with_international_transfers > 0:
            context_flags.append("international_transfers_present")
        if high_risk_without_dpia_count > 0:
            context_flags.append("high_risk_without_dpia_present")

        return {
            "total_activities": total_activities,
            "by_status": by_status,
            "by_legal_basis": by_legal_basis,
            "requires_dpia_count": requires_dpia_count,
            "with_international_transfers": with_international_transfers,
            "with_special_categories": with_special_categories,
            "missing_dpia_count": missing_dpia_count,
            "stale_activity_count": stale_activity_count,
            "high_risk_without_dpia_count": high_risk_without_dpia_count,
            "context_flags": context_flags,
        }

    def generate_article30_report(self, org_id: uuid.UUID) -> dict:
        rows = self.db.execute(
            select(ProcessingActivity).where(
                ProcessingActivity.organization_id == org_id,
                ProcessingActivity.deleted_at.is_(None),
            ).order_by(ProcessingActivity.name.asc())
        ).scalars().all()

        activities = [
            {
                "activity_id": str(row.id),
                "name": row.name,
                "purpose": row.purpose,
                "legal_basis": row.legal_basis,
                "data_categories": row.data_categories or [],
                "special_categories": row.special_categories or [],
                "data_subject_types": row.data_subject_types or [],
                "retention_period": row.retention_period,
                "recipients": row.recipients or [],
                "international_transfers": row.international_transfers,
                "transfer_destinations": row.transfer_destinations or [],
                "transfer_safeguards": row.transfer_safeguards,
            }
            for row in rows
        ]

        # Pull organization name and a representative DPO contact from activities.
        from app.models.organization import Organization  # local import to avoid circular import side effects

        org = self.db.execute(select(Organization).where(Organization.id == org_id)).scalar_one_or_none()
        dpo_contact = next((row.dpo_contact for row in rows if row.dpo_contact), None)

        status_value = "complete" if activities else "empty"
        context_flags: list[str] = []
        if activities and not dpo_contact:
            context_flags.append("dpo_contact_missing")
        if any(item["international_transfers"] and not item["transfer_destinations"] for item in activities):
            context_flags.append("transfer_destinations_missing")
        return {
            "report_type": "gdpr_article30_ropa",
            "status": status_value,
            "generated_at": self.utcnow().isoformat(),
            "organization": {"name": org.name if org else "Unknown", "dpo_contact": dpo_contact},
            "activities": activities,
            "total_activities": len(activities),
            "message": "No processing activities have been created yet." if not activities else None,
            "context_flags": context_flags,
        }

    def soft_delete_activity(self, org_id: uuid.UUID, activity_id: uuid.UUID, user_id: uuid.UUID) -> ProcessingActivity:
        row = self._require_activity(org_id, activity_id)
        if row.status != "discontinued":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only discontinued activities can be deleted")

        row.deleted_at = self.utcnow()
        row.updated_at = row.deleted_at
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="ropa.activity_deleted",
            entity_type="processing_activity",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"deleted_at": row.deleted_at.isoformat()},
            metadata_json={"source": "api"},
        )
        return row
