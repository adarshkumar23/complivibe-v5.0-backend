import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.dpa_agreement import DPAAgreement
from app.models.email_outbox import EmailOutbox
from app.models.membership import Membership
from app.models.processing_activity import ProcessingActivity
from app.models.subprocessor import Subprocessor
from app.models.user import User
from app.models.vendor import Vendor
from app.services.audit_service import AuditService
from app.core.validation import validate_choice

ALLOWED_COUNTERPARTY_TYPES = {"processor", "sub_processor", "joint_controller", "controller"}
ALLOWED_STATUSES = {"pending", "active", "expired", "under_review", "terminated"}
ALLOWED_HIPAA_ENTITY_TYPES = {"covered_entity", "business_associate", "subcontractor"}
STATUS_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"active", "terminated"},
    "active": {"under_review", "expired", "terminated"},
    "under_review": {"active", "terminated"},
    "expired": {"active", "terminated"},
    "terminated": set(),
}


class DPAService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _require_dpa(self, org_id: uuid.UUID, dpa_id: uuid.UUID) -> DPAAgreement:
        row = self.db.execute(
            select(DPAAgreement).where(
                DPAAgreement.organization_id == org_id,
                DPAAgreement.id == dpa_id,
                DPAAgreement.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DPA agreement not found")
        return row

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

    def _require_vendor(self, org_id: uuid.UUID, vendor_id: uuid.UUID) -> Vendor:
        row = self.db.execute(
            select(Vendor).where(
                Vendor.organization_id == org_id,
                Vendor.id == vendor_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")
        return row

    def _require_subprocessor(self, org_id: uuid.UUID, subprocessor_id: uuid.UUID) -> Subprocessor:
        row = self.db.execute(
            select(Subprocessor).where(
                Subprocessor.organization_id == org_id,
                Subprocessor.id == subprocessor_id,
                Subprocessor.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subprocessor not found")
        return row

    def _require_owner(self, org_id: uuid.UUID, owner_id: uuid.UUID) -> User:
        row = self.db.execute(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(
                User.id == owner_id,
                Membership.organization_id == org_id,
                Membership.status == "active",
                User.is_active.is_(True),
                User.status == "active",
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="owner_id must be an active organization user")
        return row

    @staticmethod
    def _normalize_uuid_list(values: list | None) -> list[str]:
        normalized: list[str] = []
        for item in values or []:
            try:
                parsed = uuid.UUID(str(item))
            except Exception as exc:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid UUID in list") from exc
            text = str(parsed)
            if text not in normalized:
                normalized.append(text)
        return normalized

    def _normalize_activity_ids(self, org_id: uuid.UUID, values: list | None) -> list[str]:
        normalized = self._normalize_uuid_list(values)
        for activity_id in normalized:
            self._require_activity(org_id, uuid.UUID(activity_id))
        return normalized

    def _validate_payload(self, payload: dict) -> None:
        if payload.get("counterparty_type") is not None and payload["counterparty_type"] not in ALLOWED_COUNTERPARTY_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid counterparty_type")
        if payload.get("status") is not None and payload["status"] not in ALLOWED_STATUSES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid status")
        if payload.get("renewal_notice_days") is not None and int(payload["renewal_notice_days"]) < 0:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="renewal_notice_days must be >= 0")
        if payload.get("baa_breach_notification_days") is not None and int(payload["baa_breach_notification_days"]) < 0:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="baa_breach_notification_days must be >= 0")
        if payload.get("hipaa_covered_entity_type") is not None and payload["hipaa_covered_entity_type"] not in ALLOWED_HIPAA_ENTITY_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid hipaa_covered_entity_type")

    def create_dpa(self, org_id: uuid.UUID, data, created_by: uuid.UUID) -> DPAAgreement:
        payload = data.model_dump()
        self._validate_payload(payload)
        self._require_owner(org_id, payload["owner_id"])
        if payload.get("vendor_id") is not None:
            self._require_vendor(org_id, payload["vendor_id"])
        if payload.get("subprocessor_id") is not None:
            self._require_subprocessor(org_id, payload["subprocessor_id"])
        processing_activity_ids = self._normalize_activity_ids(org_id, payload.get("processing_activity_ids") or [])

        now = self.utcnow()
        row = DPAAgreement(
            organization_id=org_id,
            counterparty_name=payload["counterparty_name"],
            counterparty_type=payload["counterparty_type"],
            vendor_id=payload.get("vendor_id"),
            subprocessor_id=payload.get("subprocessor_id"),
            dpa_reference=payload.get("dpa_reference"),
            status=payload.get("status") or "pending",
            signed_date=payload.get("signed_date"),
            effective_date=payload.get("effective_date"),
            expiry_date=payload.get("expiry_date"),
            auto_renews=bool(payload.get("auto_renews", False)),
            renewal_notice_days=int(payload.get("renewal_notice_days", 30)),
            governing_regulation=list(payload.get("governing_regulation") or []),
            article28_compliant=payload.get("article28_compliant"),
            sccs_included=payload.get("sccs_included"),
            bcrs_included=payload.get("bcrs_included"),
            data_transfer_countries=list(payload.get("data_transfer_countries") or []),
            processing_activity_ids=processing_activity_ids,
            is_baa=bool(payload.get("is_baa", False)),
            baa_effective_date=payload.get("baa_effective_date"),
            baa_includes_phi=bool(payload.get("baa_includes_phi", False)),
            baa_subcontractor_clause=bool(payload.get("baa_subcontractor_clause", False)),
            baa_breach_notification_days=int(payload.get("baa_breach_notification_days", 60)),
            hipaa_covered_entity_type=payload.get("hipaa_covered_entity_type"),
            review_notes=payload.get("review_notes"),
            owner_id=payload["owner_id"],
            created_by=created_by,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="dpa.created",
            entity_type="dpa_agreement",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={"status": row.status, "counterparty_type": row.counterparty_type},
            metadata_json={"source": "api"},
        )
        return row

    def get_dpa(self, org_id: uuid.UUID, dpa_id: uuid.UUID) -> DPAAgreement:
        return self._require_dpa(org_id, dpa_id)

    def list_dpas(
        self,
        org_id: uuid.UUID,
        status_filter: str | None = None,
        counterparty_type: str | None = None,
        vendor_id: uuid.UUID | None = None,
        subprocessor_id: uuid.UUID | None = None,
    ) -> list[DPAAgreement]:
        stmt = select(DPAAgreement).where(
            DPAAgreement.organization_id == org_id,
            DPAAgreement.deleted_at.is_(None),
        )
        if status_filter is not None:
            status_filter = validate_choice(status_filter, ALLOWED_STATUSES, "status")
            stmt = stmt.where(DPAAgreement.status == status_filter)
        if counterparty_type is not None:
            counterparty_type = validate_choice(counterparty_type, ALLOWED_COUNTERPARTY_TYPES, "counterparty_type")
            stmt = stmt.where(DPAAgreement.counterparty_type == counterparty_type)
        if vendor_id is not None:
            stmt = stmt.where(DPAAgreement.vendor_id == vendor_id)
        if subprocessor_id is not None:
            stmt = stmt.where(DPAAgreement.subprocessor_id == subprocessor_id)

        return self.db.execute(stmt.order_by(DPAAgreement.created_at.desc())).scalars().all()

    def update_dpa(self, org_id: uuid.UUID, dpa_id: uuid.UUID, data, actor_user_id: uuid.UUID) -> DPAAgreement:
        row = self._require_dpa(org_id, dpa_id)
        payload = data.model_dump(exclude_unset=True)
        self._validate_payload(payload)
        if "status" in payload and payload["status"] != row.status:
            new_status = payload["status"]
            allowed = STATUS_TRANSITIONS.get(row.status, set())
            if new_status not in allowed:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Invalid status transition from {row.status} to {new_status}",
                )
        if payload.get("owner_id") is not None:
            self._require_owner(org_id, payload["owner_id"])
        if payload.get("vendor_id") is not None:
            self._require_vendor(org_id, payload["vendor_id"])
        if payload.get("subprocessor_id") is not None:
            self._require_subprocessor(org_id, payload["subprocessor_id"])
        if "processing_activity_ids" in payload:
            payload["processing_activity_ids"] = self._normalize_activity_ids(
                org_id,
                payload.get("processing_activity_ids") or [],
            )

        for key, value in payload.items():
            setattr(row, key, value)
        row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="dpa.updated",
            entity_type="dpa_agreement",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={"status": row.status, "counterparty_type": row.counterparty_type},
            metadata_json={"source": "api"},
        )
        return row

    def transition_status(self, org_id: uuid.UUID, dpa_id: uuid.UUID, new_status: str, user_id: uuid.UUID) -> DPAAgreement:
        row = self._require_dpa(org_id, dpa_id)
        new_status = validate_choice(new_status, ALLOWED_STATUSES, "status")
        allowed = STATUS_TRANSITIONS.get(row.status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status transition from {row.status} to {new_status}",
            )

        row.status = new_status
        row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="dpa.status_changed",
            entity_type="dpa_agreement",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def link_processing_activity(self, org_id: uuid.UUID, dpa_id: uuid.UUID, activity_id: uuid.UUID, user_id: uuid.UUID) -> DPAAgreement:
        row = self._require_dpa(org_id, dpa_id)
        self._require_activity(org_id, activity_id)

        existing = self._normalize_uuid_list(row.processing_activity_ids or [])
        marker = str(activity_id)
        if marker not in existing:
            existing.append(marker)
        row.processing_activity_ids = existing
        row.updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="dpa.activity_linked",
            entity_type="dpa_agreement",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"processing_activity_ids": existing},
            metadata_json={"source": "api"},
        )
        return row

    def _queue_expiry_notice(self, row: DPAAgreement) -> None:
        owner = self.db.execute(select(User).where(User.id == row.owner_id)).scalar_one_or_none()
        if owner is None or not owner.email:
            return
        now = self.utcnow()
        self.db.add(
            EmailOutbox(
                organization_id=row.organization_id,
                template_id=None,
                event_type="dpa.expiry_notice",
                recipient_email=owner.email,
                recipient_user_id=owner.id,
                subject=f"DPA expiring soon: {row.counterparty_name}",
                body_text=(
                    f"DPA with '{row.counterparty_name}' is expiring on {row.expiry_date}. "
                    "Please review renewal requirements."
                ),
                body_html=None,
                status="pending",
                priority="high",
                scheduled_at=None,
                queued_at=now,
                sent_at=None,
                failed_at=None,
                cancelled_at=None,
                locked_at=None,
                locked_by=None,
                lock_expires_at=None,
                last_attempt_at=None,
                next_attempt_at=None,
                dead_lettered_at=None,
                attempt_count=0,
                max_attempts=3,
                last_error=None,
                provider=None,
                provider_message_id=None,
                metadata_json={"source": "dpa", "dpa_id": str(row.id)},
                worker_metadata_json=None,
                created_by_user_id=row.created_by,
            )
        )

    def run_expiry_sweep(self, org_id: uuid.UUID | None = None) -> dict:
        today = date.today()

        base_filters = [
            DPAAgreement.deleted_at.is_(None),
            DPAAgreement.status == "active",
            DPAAgreement.expiry_date.is_not(None),
        ]
        if org_id is not None:
            base_filters.append(DPAAgreement.organization_id == org_id)

        soon_rows = self.db.execute(
            select(DPAAgreement).where(
                *base_filters,
                DPAAgreement.expiry_date <= today + timedelta(days=30),
                DPAAgreement.expiry_date >= today,
            )
        ).scalars().all()

        expiring_soon = 0
        for row in soon_rows:
            notice_days = int(row.renewal_notice_days or 30)
            if row.expiry_date is None:
                continue
            if row.expiry_date <= today + timedelta(days=notice_days):
                self._queue_expiry_notice(row)
                expiring_soon += 1

        expired_rows = self.db.execute(
            select(DPAAgreement).where(
                *base_filters,
                DPAAgreement.expiry_date < today,
            )
        ).scalars().all()

        expired = 0
        now = self.utcnow()
        for row in expired_rows:
            row.status = "expired"
            row.updated_at = now
            expired += 1
            AuditService(self.db).write_audit_log(
                action="dpa.expired",
                entity_type="dpa_agreement",
                entity_id=row.id,
                organization_id=row.organization_id,
                actor_user_id=None,
                after_json={"status": row.status, "expiry_date": row.expiry_date.isoformat() if row.expiry_date else None},
                metadata_json={"source": "scheduler"},
            )

        self.db.flush()
        return {"expiring_soon": expiring_soon, "expired": expired}

    def get_dpa_summary(self, org_id: uuid.UUID) -> dict:
        base_filters = [
            DPAAgreement.organization_id == org_id,
            DPAAgreement.deleted_at.is_(None),
        ]

        total = int(self.db.execute(select(func.count(DPAAgreement.id)).where(*base_filters)).scalar_one() or 0)

        status_rows = self.db.execute(
            select(DPAAgreement.status, func.count(DPAAgreement.id)).where(*base_filters).group_by(DPAAgreement.status)
        ).all()
        by_status = {str(key): int(value) for key, value in status_rows}

        type_rows = self.db.execute(
            select(DPAAgreement.counterparty_type, func.count(DPAAgreement.id))
            .where(*base_filters)
            .group_by(DPAAgreement.counterparty_type)
        ).all()
        by_type = {str(key): int(value) for key, value in type_rows}

        article28_compliant_count = int(
            self.db.execute(
                select(func.count(DPAAgreement.id)).where(*base_filters, DPAAgreement.article28_compliant.is_(True))
            ).scalar_one()
            or 0
        )

        expiring_soon_30d = int(
            self.db.execute(
                select(func.count(DPAAgreement.id)).where(
                    *base_filters,
                    DPAAgreement.status == "active",
                    DPAAgreement.expiry_date.is_not(None),
                    DPAAgreement.expiry_date <= date.today() + timedelta(days=30),
                    DPAAgreement.expiry_date >= date.today(),
                )
            ).scalar_one()
            or 0
        )

        subprocessors = self.db.execute(
            select(Subprocessor).where(
                Subprocessor.organization_id == org_id,
                Subprocessor.deleted_at.is_(None),
            )
        ).scalars().all()

        linked_active_subprocessors: set[str] = set()
        active_link_rows = self.db.execute(
            select(DPAAgreement.subprocessor_id).where(
                DPAAgreement.organization_id == org_id,
                DPAAgreement.deleted_at.is_(None),
                DPAAgreement.status == "active",
                DPAAgreement.subprocessor_id.is_not(None),
            )
        ).scalars().all()
        for item in active_link_rows:
            if item is not None:
                linked_active_subprocessors.add(str(item))

        missing_dpa_count = sum(1 for s in subprocessors if str(s.id) not in linked_active_subprocessors)

        activities = self.db.execute(
            select(ProcessingActivity).where(
                ProcessingActivity.organization_id == org_id,
                ProcessingActivity.deleted_at.is_(None),
            )
        ).scalars().all()
        personal_data_activity_ids = {
            str(row.id)
            for row in activities
            if any(str(item).lower() == "personal_data" for item in (row.data_categories or []))
        }

        covered_ids: set[str] = set()
        active_dpas = self.db.execute(
            select(DPAAgreement.processing_activity_ids).where(
                DPAAgreement.organization_id == org_id,
                DPAAgreement.deleted_at.is_(None),
                DPAAgreement.status == "active",
            )
        ).scalars().all()
        for items in active_dpas:
            for item in items or []:
                token = str(item)
                if token in personal_data_activity_ids:
                    covered_ids.add(token)

        total_personal = len(personal_data_activity_ids)
        covered = len(covered_ids)
        gdpr_coverage_pct = (covered / total_personal * 100.0) if total_personal > 0 else 0.0

        return {
            "total": total,
            "by_status": by_status,
            "by_type": by_type,
            "article28_compliant_count": article28_compliant_count,
            "missing_dpa_count": missing_dpa_count,
            "expiring_soon_30d": expiring_soon_30d,
            "gdpr_coverage": {
                "total_personal_data_activities": total_personal,
                "covered_activities": covered,
                "coverage_pct": round(gdpr_coverage_pct, 2),
            },
        }

    def soft_delete_dpa(self, org_id: uuid.UUID, dpa_id: uuid.UUID, user_id: uuid.UUID) -> None:
        row = self._require_dpa(org_id, dpa_id)
        if row.status != "terminated":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only terminated DPA can be deleted")

        row.deleted_at = self.utcnow()
        row.updated_at = row.deleted_at
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="dpa.deleted",
            entity_type="dpa_agreement",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"deleted_at": row.deleted_at.isoformat()},
            metadata_json={"source": "api"},
        )


def run_daily_dpa_expiry_sweep(db: Session) -> dict:
    return DPAService(db).run_expiry_sweep(org_id=None)
