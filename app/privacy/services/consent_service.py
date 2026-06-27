import hashlib
import uuid
from datetime import UTC, date, datetime

from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.data_observability.services.lineage_service import LineageService
from app.models.consent_record import ConsentRecord
from app.models.data_asset import DataAsset
from app.models.email_outbox import EmailOutbox
from app.models.processing_activity import ProcessingActivity
from app.models.user import User
from app.services.audit_service import AuditService

ALLOWED_CONSENT_MECHANISMS = {
    "explicit_checkbox",
    "cookie_banner",
    "written_form",
    "verbal_recorded",
    "api_consent",
    "implied",
}


class ConsentService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def hash_subject_identifier(subject_identifier: str) -> str:
        return hashlib.sha256(subject_identifier.encode("utf-8")).hexdigest()

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

    def _require_consent(self, org_id: uuid.UUID, consent_id: uuid.UUID) -> ConsentRecord:
        row = self.db.execute(
            select(ConsentRecord).where(
                ConsentRecord.organization_id == org_id,
                ConsentRecord.id == consent_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consent record not found")
        return row

    def _queue_withdrawal_notifications(self, org_id: uuid.UUID, activity: ProcessingActivity, actor_user_id: uuid.UUID | None) -> int:
        asset_ids = [uuid.UUID(str(item)) for item in (activity.linked_data_asset_ids or []) if item]
        if not asset_ids:
            return 0

        assets = self.db.execute(
            select(DataAsset).where(
                DataAsset.organization_id == org_id,
                DataAsset.id.in_(asset_ids),
                DataAsset.deleted_at.is_(None),
            )
        ).scalars().all()
        if not assets:
            return 0

        owner_ids = {asset.owner_id for asset in assets}
        users = self.db.execute(
            select(User).where(User.id.in_(owner_ids), User.is_active.is_(True), User.status == "active", User.email.is_not(None))
        ).scalars().all()

        now = self.utcnow()
        for user in users:
            outbox = EmailOutbox(
                organization_id=org_id,
                template_id=None,
                event_type="consent.withdrawn",
                recipient_email=user.email,
                recipient_user_id=user.id,
                subject="Consent withdrawn for linked processing activity",
                body_text=(
                    f"Consent has been withdrawn for processing activity '{activity.name}'. "
                    "Please review linked data assets and processing flows."
                ),
                body_html=(
                    f"<p>Consent has been withdrawn for processing activity '{activity.name}'. "
                    "Please review linked data assets and processing flows.</p>"
                ),
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
                metadata_json={"source": "consent", "processing_activity_id": str(activity.id)},
                worker_metadata_json=None,
                created_by_user_id=actor_user_id,
            )
            self.db.add(outbox)
        self.db.flush()
        return len(users)

    def record_consent(
        self,
        org_id: uuid.UUID,
        activity_id: uuid.UUID,
        data,
        granted: bool = True,
        actor_user_id: uuid.UUID | None = None,
    ) -> ConsentRecord:
        activity = self._require_activity(org_id, activity_id)
        payload = data.model_dump() if hasattr(data, "model_dump") else dict(data)

        mechanism = payload.get("consent_mechanism")
        if mechanism not in ALLOWED_CONSENT_MECHANISMS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid consent_mechanism")

        subject_identifier = payload["subject_identifier"]
        subject_hash = self.hash_subject_identifier(subject_identifier)
        stored_identifier = "hashed"
        now = self.utcnow()

        row = self.db.execute(
            select(ConsentRecord).where(
                ConsentRecord.organization_id == org_id,
                ConsentRecord.processing_activity_id == activity_id,
                ConsentRecord.subject_identifier_hash == subject_hash,
            )
        ).scalar_one_or_none()

        target_granted = bool(payload.get("granted", granted))

        if row is None:
            row = ConsentRecord(
                organization_id=org_id,
                processing_activity_id=activity.id,
                notice_id=payload.get("notice_id"),
                subject_identifier=stored_identifier,
                subject_identifier_hash=subject_hash,
                consent_mechanism=mechanism,
                consent_version=payload.get("consent_version"),
                granted=target_granted,
                granted_at=now if target_granted else None,
                withdrawn_at=None if target_granted else now,
                withdrawal_reason=None if target_granted else payload.get("withdrawal_reason"),
                ip_address=payload.get("ip_address"),
                user_agent=payload.get("user_agent"),
                expiry_date=payload.get("expiry_date"),
                metadata_json=payload.get("metadata") or {},
                created_at=now,
                updated_at=now,
            )
            self.db.add(row)
        else:
            row.notice_id = payload.get("notice_id", row.notice_id)
            row.subject_identifier = stored_identifier
            row.consent_mechanism = mechanism
            row.consent_version = payload.get("consent_version", row.consent_version)
            row.granted = target_granted
            row.granted_at = now if target_granted else row.granted_at
            row.withdrawn_at = now if not target_granted else None
            row.withdrawal_reason = payload.get("withdrawal_reason") if not target_granted else None
            row.ip_address = payload.get("ip_address", row.ip_address)
            row.user_agent = payload.get("user_agent", row.user_agent)
            row.expiry_date = payload.get("expiry_date", row.expiry_date)
            if payload.get("metadata") is not None:
                row.metadata_json = payload.get("metadata") or {}
            row.updated_at = now

        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="consent.recorded",
            entity_type="consent_record",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={
                "processing_activity_id": str(activity_id),
                "subject_identifier_hash": subject_hash,
                "granted": row.granted,
                "consent_mechanism": row.consent_mechanism,
            },
            metadata_json={"source": "api"},
        )
        return row

    def withdraw_consent(
        self,
        org_id: uuid.UUID,
        consent_id: uuid.UUID,
        reason: str | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> ConsentRecord:
        row = self._require_consent(org_id, consent_id)
        activity = self._require_activity(org_id, row.processing_activity_id)

        now = self.utcnow()
        row.granted = False
        row.withdrawn_at = now
        row.withdrawal_reason = reason
        row.updated_at = now
        self.db.flush()

        notified = self._queue_withdrawal_notifications(org_id, activity, actor_user_id)

        AuditService(self.db).write_audit_log(
            action="consent.withdrawn",
            entity_type="consent_record",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={"withdrawn_at": row.withdrawn_at.isoformat(), "reason": reason, "notified_asset_owners": notified},
            metadata_json={"source": "api"},
        )
        return row

    def get_consent_status(self, org_id: uuid.UUID, activity_id: uuid.UUID, subject_identifier: str) -> dict:
        self._require_activity(org_id, activity_id)
        subject_hash = self.hash_subject_identifier(subject_identifier)
        row = self.db.execute(
            select(ConsentRecord).where(
                ConsentRecord.organization_id == org_id,
                ConsentRecord.processing_activity_id == activity_id,
                ConsentRecord.subject_identifier_hash == subject_hash,
            )
        ).scalar_one_or_none()

        if row is None:
            return {
                "has_consent": False,
                "granted_at": None,
                "withdrawn_at": None,
                "consent_mechanism": None,
            }

        return {
            "has_consent": bool(row.granted),
            "granted_at": row.granted_at,
            "withdrawn_at": row.withdrawn_at,
            "consent_mechanism": row.consent_mechanism,
        }

    def list_consents(
        self,
        org_id: uuid.UUID,
        activity_id: uuid.UUID | None = None,
        granted: bool | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ConsentRecord]:
        stmt = select(ConsentRecord).where(ConsentRecord.organization_id == org_id)
        if activity_id is not None:
            stmt = stmt.where(ConsentRecord.processing_activity_id == activity_id)
        if granted is not None:
            stmt = stmt.where(ConsentRecord.granted.is_(granted))

        return self.db.execute(
            stmt.order_by(ConsentRecord.created_at.desc()).offset(max(0, int(skip))).limit(max(1, min(int(limit), 500)))
        ).scalars().all()

    def get_consent_summary(self, org_id: uuid.UUID, activity_id: uuid.UUID | None = None) -> dict:
        base_filters = [ConsentRecord.organization_id == org_id]
        if activity_id is not None:
            base_filters.append(ConsentRecord.processing_activity_id == activity_id)

        total = int(self.db.execute(select(func.count(ConsentRecord.id)).where(*base_filters)).scalar_one() or 0)
        active_consents = int(
            self.db.execute(select(func.count(ConsentRecord.id)).where(*base_filters, ConsentRecord.granted.is_(True))).scalar_one() or 0
        )
        withdrawn_count = int(
            self.db.execute(select(func.count(ConsentRecord.id)).where(*base_filters, ConsentRecord.granted.is_(False))).scalar_one() or 0
        )

        today = date.today()
        expired_count = int(
            self.db.execute(
                select(func.count(ConsentRecord.id)).where(
                    *base_filters,
                    ConsentRecord.expiry_date.is_not(None),
                    ConsentRecord.expiry_date < today,
                )
            ).scalar_one()
            or 0
        )

        consent_rate = (active_consents / total * 100) if total > 0 else 0.0
        return {
            "total_records": total,
            "active_consents": active_consents,
            "withdrawn_count": withdrawn_count,
            "expired_count": expired_count,
            "consent_rate_pct": round(consent_rate, 2),
        }

    def sweep_expired_consents(self) -> dict:
        now = self.utcnow()
        today = date.today()

        rows = self.db.execute(
            select(ConsentRecord).where(
                ConsentRecord.expiry_date.is_not(None),
                ConsentRecord.expiry_date < today,
                ConsentRecord.granted.is_(True),
            )
        ).scalars().all()

        expired = 0
        for row in rows:
            row.granted = False
            row.withdrawn_at = now
            row.withdrawal_reason = "expired"
            row.updated_at = now
            expired += 1

            AuditService(self.db).write_audit_log(
                action="consent.expired",
                entity_type="consent_record",
                entity_id=row.id,
                organization_id=row.organization_id,
                actor_user_id=None,
                after_json={"withdrawal_reason": "expired", "withdrawn_at": row.withdrawn_at.isoformat()},
                metadata_json={"source": "scheduler"},
            )

        self.db.flush()
        return {"expired": expired}

    def resolve_org_by_api_key(self, raw_key: str) -> uuid.UUID:
        return LineageService(self.db).resolve_org_by_api_key(raw_key)

    def receive_inbound_event(self, raw_key: str, payload) -> ConsentRecord:
        org_id = self.resolve_org_by_api_key(raw_key)
        event_payload = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
        activity_id = event_payload["processing_activity_id"]
        return self.record_consent(org_id, activity_id, event_payload, granted=bool(event_payload.get("granted", True)), actor_user_id=None)


def run_daily_consent_expiry_sweep(db: Session) -> dict:
    return ConsentService(db).sweep_expired_consents()
