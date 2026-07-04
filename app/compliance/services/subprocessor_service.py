import uuid
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.email_outbox import EmailOutbox
from app.models.subprocessor import Subprocessor
from app.models.subprocessor_data_transfer import SubprocessorDataTransfer
from app.models.user import User
from app.services.audit_service import AuditService


class SubprocessorService:
    EEA_COUNTRIES = {
        "AT",
        "BE",
        "BG",
        "CY",
        "CZ",
        "DE",
        "DK",
        "EE",
        "ES",
        "FI",
        "FR",
        "GR",
        "HR",
        "HU",
        "IE",
        "IS",
        "IT",
        "LI",
        "LT",
        "LU",
        "LV",
        "MT",
        "NL",
        "NO",
        "PL",
        "PT",
        "RO",
        "SE",
        "SI",
        "SK",
        "GB",
    }

    DPA_TRANSITIONS: dict[str, set[str]] = {
        "pending": {"signed", "not_required", "under_review"},
        "signed": {"expired", "under_review"},
        "expired": {"signed", "under_review"},
        "under_review": {"signed", "not_required"},
        "not_required": {"under_review"},
    }

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def utcdate() -> date:
        return datetime.now(UTC).date()

    def _require_user(self, user_id: uuid.UUID) -> User:
        row = self.db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="user_id not found")
        return row

    def require_subprocessor(self, org_id: uuid.UUID, subprocessor_id: uuid.UUID) -> Subprocessor:
        row = self.db.execute(
            select(Subprocessor).where(
                Subprocessor.id == subprocessor_id,
                Subprocessor.organization_id == org_id,
                Subprocessor.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subprocessor not found")
        return row

    def _validate_gdpr_required_fields(self, data, existing: Subprocessor | None = None) -> None:
        updates = data.model_dump(exclude_unset=True) if hasattr(data, "model_dump") else {}

        def effective(field_name: str):
            if field_name in updates:
                return updates[field_name]
            if existing is not None:
                return getattr(existing, field_name)
            return getattr(data, field_name, None)

        missing: list[str] = []
        data_types = effective("data_types_processed")
        if not data_types:
            missing.append("data_types_processed")
        locations = effective("geographic_locations")
        if not locations:
            missing.append("geographic_locations")
        mechanism = effective("data_transfer_mechanism")
        if locations:
            non_eea = [loc for loc in locations if loc not in self.EEA_COUNTRIES]
            if non_eea and not mechanism:
                missing.append("data_transfer_mechanism (required for non-EEA transfers)")
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Missing GDPR Article 28 required fields: {', '.join(missing)}",
            )

    def create_subprocessor(self, org_id: uuid.UUID, data, created_by: uuid.UUID) -> Subprocessor:
        self._require_user(created_by)
        self._validate_gdpr_required_fields(data)
        row = Subprocessor(
            organization_id=org_id,
            name=data.name,
            service_description=data.service_description,
            data_types_processed=data.data_types_processed,
            legal_basis=data.legal_basis,
            geographic_locations=data.geographic_locations,
            data_transfer_mechanism=data.data_transfer_mechanism,
            dpa_status=data.dpa_status,
            dpa_signed_at=data.dpa_signed_at,
            dpa_expiry_date=data.dpa_expiry_date,
            dpa_document_ref=data.dpa_document_ref,
            controller_type=data.controller_type,
            risk_level=data.risk_level,
            status=data.status,
            contact_name=data.contact_name,
            contact_email=data.contact_email,
            review_due_date=data.review_due_date,
            created_by=created_by,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="subprocessor.created",
            entity_type="subprocessor",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={"name": row.name, "status": row.status, "dpa_status": row.dpa_status},
            metadata_json={"source": "api"},
        )
        return row

    def get_subprocessor(self, org_id: uuid.UUID, subprocessor_id: uuid.UUID) -> Subprocessor:
        return self.require_subprocessor(org_id, subprocessor_id)

    def list_subprocessors(
        self,
        org_id: uuid.UUID,
        *,
        status_value: str | None = None,
        dpa_status: str | None = None,
        risk_level: str | None = None,
        controller_type: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Subprocessor]:
        stmt = select(Subprocessor).where(
            Subprocessor.organization_id == org_id,
            Subprocessor.deleted_at.is_(None),
        )
        if status_value is not None:
            stmt = stmt.where(Subprocessor.status == status_value)
        if dpa_status is not None:
            stmt = stmt.where(Subprocessor.dpa_status == dpa_status)
        if risk_level is not None:
            stmt = stmt.where(Subprocessor.risk_level == risk_level)
        if controller_type is not None:
            stmt = stmt.where(Subprocessor.controller_type == controller_type)
        return self.db.execute(stmt.order_by(Subprocessor.created_at.desc()).offset(skip).limit(limit)).scalars().all()

    def update_subprocessor(self, org_id: uuid.UUID, subprocessor_id: uuid.UUID, data, *, actor_user_id: uuid.UUID | None = None) -> Subprocessor:
        row = self.require_subprocessor(org_id, subprocessor_id)
        self._validate_gdpr_required_fields(data, existing=row)
        updates = data.model_dump(exclude_unset=True)

        before = {
            "name": row.name,
            "status": row.status,
            "dpa_status": row.dpa_status,
            "risk_level": row.risk_level,
        }
        for key, value in updates.items():
            setattr(row, key, value)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="subprocessor.updated",
            entity_type="subprocessor",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json={
                "name": row.name,
                "status": row.status,
                "dpa_status": row.dpa_status,
                "risk_level": row.risk_level,
            },
            metadata_json={"source": "api"},
        )
        return row

    def update_dpa_status(
        self,
        org_id: uuid.UUID,
        subprocessor_id: uuid.UUID,
        new_status: str,
        user_id: uuid.UUID,
        *,
        signed_at: datetime | None = None,
        expiry_date: date | None = None,
    ) -> Subprocessor:
        row = self.require_subprocessor(org_id, subprocessor_id)
        allowed = self.DPA_TRANSITIONS.get(row.dpa_status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid DPA status transition from {row.dpa_status} to {new_status}",
            )

        before = {
            "dpa_status": row.dpa_status,
            "dpa_signed_at": row.dpa_signed_at.isoformat() if row.dpa_signed_at else None,
            "dpa_expiry_date": row.dpa_expiry_date.isoformat() if row.dpa_expiry_date else None,
        }

        row.dpa_status = new_status
        if new_status == "signed":
            row.dpa_signed_at = signed_at or self.utcnow()
            if expiry_date is not None:
                row.dpa_expiry_date = expiry_date
        elif expiry_date is not None:
            row.dpa_expiry_date = expiry_date

        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="subprocessor.dpa_status_updated",
            entity_type="subprocessor",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            before_json=before,
            after_json={
                "dpa_status": row.dpa_status,
                "dpa_signed_at": row.dpa_signed_at.isoformat() if row.dpa_signed_at else None,
                "dpa_expiry_date": row.dpa_expiry_date.isoformat() if row.dpa_expiry_date else None,
            },
            metadata_json={"source": "api"},
        )
        return row

    def add_data_transfer(self, org_id: uuid.UUID, subprocessor_id: uuid.UUID, data, *, actor_user_id: uuid.UUID | None = None) -> SubprocessorDataTransfer:
        _ = self.require_subprocessor(org_id, subprocessor_id)
        row = SubprocessorDataTransfer(
            organization_id=org_id,
            subprocessor_id=subprocessor_id,
            origin_country=data.origin_country,
            destination_country=data.destination_country,
            data_categories=data.data_categories,
            transfer_mechanism=data.transfer_mechanism,
            legal_basis=data.legal_basis,
            is_active=data.is_active,
            notes=data.notes,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="subprocessor.transfer_added",
            entity_type="subprocessor_data_transfer",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={
                "subprocessor_id": str(subprocessor_id),
                "origin_country": row.origin_country,
                "destination_country": row.destination_country,
            },
            metadata_json={"source": "api"},
        )
        return row

    def list_data_transfers(self, org_id: uuid.UUID, subprocessor_id: uuid.UUID) -> list[SubprocessorDataTransfer]:
        _ = self.require_subprocessor(org_id, subprocessor_id)
        return self.db.execute(
            select(SubprocessorDataTransfer)
            .where(
                SubprocessorDataTransfer.organization_id == org_id,
                SubprocessorDataTransfer.subprocessor_id == subprocessor_id,
            )
            .order_by(SubprocessorDataTransfer.created_at.desc())
        ).scalars().all()

    def mark_reviewed(self, org_id: uuid.UUID, subprocessor_id: uuid.UUID, user_id: uuid.UUID) -> Subprocessor:
        row = self.require_subprocessor(org_id, subprocessor_id)
        now = self.utcnow()
        row.last_reviewed_at = now
        row.last_reviewed_by = user_id
        row.review_due_date = (now + timedelta(days=365)).date()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="subprocessor.reviewed",
            entity_type="subprocessor",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={
                "last_reviewed_at": row.last_reviewed_at.isoformat() if row.last_reviewed_at else None,
                "review_due_date": row.review_due_date.isoformat() if row.review_due_date else None,
            },
            metadata_json={"source": "api"},
        )
        return row

    def _queue_dpa_reminder(self, row: Subprocessor, *, days_until: int) -> int:
        queued = 0
        subject = f"DPA renewal reminder: {row.name}"
        body = (
            f"Subprocessor: {row.name}\n"
            f"DPA status: {row.dpa_status}\n"
            f"DPA expiry date: {row.dpa_expiry_date.isoformat() if row.dpa_expiry_date else 'N/A'}\n"
            f"Days until expiry: {days_until}\n"
        )

        recipients = self.db.execute(
            select(User).where(
                User.id.in_([row.created_by, row.last_reviewed_by] if row.last_reviewed_by else [row.created_by]),
                User.is_active.is_(True),
                User.status == "active",
                User.email.is_not(None),
            )
        ).scalars().all()

        recipient_ids: set[uuid.UUID] = set()
        for recipient in recipients:
            if recipient.id in recipient_ids:
                continue
            recipient_ids.add(recipient.id)
            self.db.add(
                EmailOutbox(
                    organization_id=row.organization_id,
                    template_id=None,
                    event_type="subprocessor.dpa.expiry.reminder",
                    recipient_email=recipient.email,
                    recipient_user_id=recipient.id,
                    subject=subject,
                    body_text=body,
                    body_html=None,
                    status="pending",
                    priority="normal",
                    scheduled_at=None,
                    queued_at=self.utcnow(),
                    attempt_count=0,
                    max_attempts=3,
                    metadata_json={
                        "source": "subprocessor_dpa_expiry_sweep",
                        "subprocessor_id": str(row.id),
                        "dpa_expiry_date": row.dpa_expiry_date.isoformat() if row.dpa_expiry_date else None,
                    },
                    created_by_user_id=row.created_by,
                )
            )
            queued += 1
        return queued

    def sweep_expired_dpas(self, org_id: uuid.UUID | None = None) -> dict[str, int]:
        today = self.utcdate()
        threshold = today + timedelta(days=30)

        stmt = select(Subprocessor).where(
            Subprocessor.deleted_at.is_(None),
            Subprocessor.dpa_status == "signed",
            Subprocessor.dpa_expiry_date.is_not(None),
        )
        if org_id is not None:
            stmt = stmt.where(Subprocessor.organization_id == org_id)

        rows = self.db.execute(stmt).scalars().all()

        expiring_soon = 0
        expired = 0
        reminders_queued = 0
        per_org = defaultdict(lambda: {"expiring_soon": 0, "expired": 0, "reminders_queued": 0})

        for row in rows:
            if row.dpa_expiry_date is None:
                continue

            if row.dpa_expiry_date < today and row.dpa_status == "signed":
                row.dpa_status = "expired"
                expired += 1
                per_org[row.organization_id]["expired"] += 1
                continue

            if row.dpa_expiry_date <= threshold and row.dpa_status == "signed":
                expiring_soon += 1
                per_org[row.organization_id]["expiring_soon"] += 1
                queued = self._queue_dpa_reminder(row, days_until=(row.dpa_expiry_date - today).days)
                reminders_queued += queued
                per_org[row.organization_id]["reminders_queued"] += queued

        self.db.flush()

        for audit_org_id, counts in per_org.items():
            AuditService(self.db).write_audit_log(
                action="subprocessor.dpa_expiry_swept",
                entity_type="subprocessor",
                organization_id=audit_org_id,
                actor_user_id=None,
                after_json=counts,
                metadata_json={"source": "scheduler"},
            )

        return {
            "expiring_soon": expiring_soon,
            "expired": expired,
            "reminders_queued": reminders_queued,
        }

    def get_gdpr_dashboard(self, org_id: uuid.UUID) -> dict:
        today = self.utcdate()
        window_end = today + timedelta(days=30)

        rows = self.db.execute(
            select(Subprocessor).where(
                Subprocessor.organization_id == org_id,
                Subprocessor.deleted_at.is_(None),
            )
        ).scalars().all()

        by_status = Counter(row.status for row in rows)
        by_dpa_status = Counter(row.dpa_status for row in rows)
        by_risk_level = Counter(row.risk_level for row in rows)

        subprocessor_ids_with_explicit_transfer = set(
            self.db.execute(
                select(SubprocessorDataTransfer.subprocessor_id).where(
                    SubprocessorDataTransfer.organization_id == org_id,
                    SubprocessorDataTransfer.is_active.is_(True),
                    SubprocessorDataTransfer.destination_country.not_in(sorted(self.EEA_COUNTRIES)),
                )
            ).scalars().all()
        )
        subprocessor_ids_with_non_eea_locations = {
            row.id for row in rows if set(row.geographic_locations or []) - self.EEA_COUNTRIES
        }
        transfers_outside_eea = len(subprocessor_ids_with_explicit_transfer | subprocessor_ids_with_non_eea_locations)

        review_overdue_count = int(
            self.db.execute(
                select(func.count(Subprocessor.id)).where(
                    Subprocessor.organization_id == org_id,
                    Subprocessor.deleted_at.is_(None),
                    Subprocessor.status == "active",
                    Subprocessor.review_due_date.is_not(None),
                    Subprocessor.review_due_date < today,
                )
            ).scalar_one()
        )

        expiring_dpa_30_days = int(
            self.db.execute(
                select(func.count(Subprocessor.id)).where(
                    Subprocessor.organization_id == org_id,
                    Subprocessor.deleted_at.is_(None),
                    Subprocessor.dpa_status == "signed",
                    Subprocessor.dpa_expiry_date.is_not(None),
                    Subprocessor.dpa_expiry_date <= window_end,
                )
            ).scalar_one()
        )

        return {
            "total_subprocessors": len(rows),
            "by_status": {k: int(v) for k, v in by_status.items()},
            "by_dpa_status": {k: int(v) for k, v in by_dpa_status.items()},
            "by_risk_level": {k: int(v) for k, v in by_risk_level.items()},
            "missing_dpa_count": int(by_dpa_status.get("pending", 0) + by_dpa_status.get("expired", 0)),
            "high_risk_count": int(by_risk_level.get("high", 0) + by_risk_level.get("critical", 0)),
            "transfers_outside_eea": transfers_outside_eea,
            "review_overdue_count": review_overdue_count,
            "expiring_dpa_30_days": expiring_dpa_30_days,
        }

    def soft_delete_subprocessor(self, org_id: uuid.UUID, subprocessor_id: uuid.UUID, user_id: uuid.UUID) -> Subprocessor:
        row = self.require_subprocessor(org_id, subprocessor_id)
        if row.status not in {"inactive", "offboarded"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only inactive/offboarded subprocessors can be deleted")

        before = {"status": row.status, "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None}
        row.deleted_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="subprocessor.deleted",
            entity_type="subprocessor",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            before_json=before,
            after_json={"status": row.status, "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None},
            metadata_json={"source": "api"},
        )
        return row


def run_daily_subprocessor_dpa_expiry_sweep(db: Session) -> dict[str, int]:
    return SubprocessorService(db).sweep_expired_dpas()
