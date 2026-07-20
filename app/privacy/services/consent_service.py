import hashlib
import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.services.subsystem_ingest_key_service import SubsystemIngestKeyService
from app.models.consent_record import ConsentRecord
from app.models.data_asset import DataAsset
from app.models.email_outbox import EmailOutbox
from app.models.google_consent_mode_event import GoogleConsentModeEvent
from app.models.processing_activity import ProcessingActivity
from app.models.user import User
from app.services.audit_service import AuditService
from app.core.validation import validate_choice

ALLOWED_CONSENT_MECHANISMS = {
    "explicit_checkbox",
    "cookie_banner",
    "written_form",
    "verbal_recorded",
    "api_consent",
    "implied",
    "ccpa_opt_out",
}

GCM_V2_STATES = {"granted", "denied"}

# DPDP Act 2023 Section 9: processing a child's personal data requires verifiable
# consent of a parent, and processing a person-with-disability's data requires
# verifiable consent of a lawful guardian appointed by a court/designated authority.
ALLOWED_GUARDIAN_RELATIONSHIPS = {"parent", "lawful_guardian_disability"}
ALLOWED_GUARDIAN_VERIFICATION_METHODS = {
    "government_id_token",
    "digilocker",
    "existing_reliable_id",
    "court_authority_appointment",
}

# ISO 3166-1 alpha-2 codes for the jurisdictions where Google requires all four
# Consent Mode v2 signals to default to "denied" until the visitor interacts
# with a consent banner: the 27 EU/EEA member states, the additional EEA states
# (Iceland, Liechtenstein, Norway), the United Kingdom, and Switzerland.
# Source: https://support.google.com/tagmanager/answer/13695607 (traffic
# outside this list defaults to "granted").
EEA_UK_CH_REGION_CODES = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
    "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
    "SI", "ES", "SE",  # EU member states
    "IS", "LI", "NO",  # additional EEA states
    "GB", "CH",  # UK and Switzerland (Google treats these the same as EEA)
}
# Also accept the common shorthand region value "EEA" itself, since many
# callers (and Google's own Tag Manager UI) use that literal label rather
# than enumerating member country codes.
_RESTRICTED_REGION_LABELS = {"EEA", "EU", "EEA+UK", "EEA_UK_CH"}

# Regulatory re-consent window: the UK ICO recommends refreshing cookie
# consent after roughly 6 months, while EDPB commentary and most national
# DPAs converge on 12 months as the outer bound. We flag consent as stale
# once it exceeds 365 days so a compliance officer can decide whether to
# re-prompt, using the more conservative (longer) end of that range as the
# hard cutoff rather than silently expiring signals early.
GCM_RECONSENT_STALE_DAYS = 365


def _is_restricted_default_region(region: str | None) -> bool | None:
    """Return True if `region` is a jurisdiction where Google requires consent
    signals to default to denied (EEA/UK/Switzerland), False if it is clearly
    outside that list, or None if no region was supplied (unknown)."""
    if not region:
        return None
    normalized = region.strip().upper()
    if normalized in _RESTRICTED_REGION_LABELS:
        return True
    return normalized in EEA_UK_CH_REGION_CODES


class ConsentService:
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

    def consent_context(self, row: ConsentRecord, *, now: datetime | None = None) -> dict:
        evaluated_now = now or self.utcnow()
        created_at = self._as_utc(row.created_at) or evaluated_now
        age_days = max(0, int((evaluated_now - created_at).total_seconds() // 86400))
        time_to_expiry_days: int | None = None
        is_expired = False
        if row.expiry_date is not None:
            time_to_expiry_days = (row.expiry_date - evaluated_now.date()).days
            is_expired = time_to_expiry_days < 0

        context_flags: list[str] = []
        if row.granted:
            context_flags.append("active_consent")
        else:
            context_flags.append("withdrawn_consent")
        if is_expired:
            context_flags.append("expired_consent")
            if row.granted:
                context_flags.append("expired_but_still_granted")
        elif time_to_expiry_days is not None and time_to_expiry_days <= 30:
            context_flags.append("consent_expiring_soon")
        if row.notice_id is None:
            context_flags.append("notice_reference_missing")
        if row.granted and row.withdrawn_at is not None:
            context_flags.append("state_inconsistency_granted_with_withdrawn_timestamp")
        if not row.granted and row.withdrawn_at is None:
            context_flags.append("state_inconsistency_missing_withdrawn_timestamp")
        if row.consent_mechanism == "implied":
            context_flags.append("implicit_consent")
        if row.consent_mechanism == "ccpa_opt_out":
            context_flags.append("ccpa_opt_out_record")
        return {
            "age_days": age_days,
            "time_to_expiry_days": time_to_expiry_days,
            "is_expired": is_expired,
            "context_flags": context_flags,
        }

    def consent_response_payload(self, row: ConsentRecord) -> dict:
        context = self.consent_context(row)
        return {
            "id": row.id,
            "organization_id": row.organization_id,
            "processing_activity_id": row.processing_activity_id,
            "notice_id": row.notice_id,
            "subject_identifier": row.subject_identifier,
            "subject_identifier_hash": row.subject_identifier_hash,
            "consent_mechanism": row.consent_mechanism,
            "consent_version": row.consent_version,
            "granted": row.granted,
            "granted_at": row.granted_at,
            "withdrawn_at": row.withdrawn_at,
            "withdrawal_reason": row.withdrawal_reason,
            "ip_address": row.ip_address,
            "user_agent": row.user_agent,
            "expiry_date": row.expiry_date,
            "metadata_json": row.metadata_json,
            "is_minor_or_guardian_managed": row.is_minor_or_guardian_managed,
            "guardian_relationship": row.guardian_relationship,
            "guardian_identity_reference": row.guardian_identity_reference,
            "guardian_verification_method": row.guardian_verification_method,
            "guardian_verified_at": row.guardian_verified_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "age_days": context["age_days"],
            "time_to_expiry_days": context["time_to_expiry_days"],
            "is_expired": context["is_expired"],
            "context_flags": context["context_flags"],
        }

    def consent_response_payloads(self, rows: list[ConsentRecord]) -> list[dict]:
        return [self.consent_response_payload(row) for row in rows]

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
        mechanism = validate_choice(mechanism, ALLOWED_CONSENT_MECHANISMS, "consent_mechanism")

        is_guardian_managed = bool(payload.get("is_minor_or_guardian_managed", False))
        guardian_relationship = payload.get("guardian_relationship")
        guardian_verification_method = payload.get("guardian_verification_method")
        if is_guardian_managed:
            if not guardian_relationship or not guardian_verification_method:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="guardian_relationship and guardian_verification_method are required when "
                    "is_minor_or_guardian_managed is true (DPDP Act 2023 Section 9 verifiable consent)",
                )
            guardian_relationship = validate_choice(guardian_relationship, ALLOWED_GUARDIAN_RELATIONSHIPS, "guardian_relationship")
            guardian_verification_method = validate_choice(
                guardian_verification_method, ALLOWED_GUARDIAN_VERIFICATION_METHODS, "guardian_verification_method"
            )
        else:
            guardian_relationship = None
            guardian_verification_method = None

        subject_identifier = payload["subject_identifier"]
        subject_hash = self.hash_subject_identifier(subject_identifier)
        stored_identifier = subject_hash
        now = self.utcnow()
        expiry_date = payload.get("expiry_date")

        row = self.db.execute(
            select(ConsentRecord).where(
                ConsentRecord.organization_id == org_id,
                ConsentRecord.processing_activity_id == activity_id,
                ConsentRecord.subject_identifier_hash == subject_hash,
            )
        ).scalar_one_or_none()

        target_granted = bool(payload.get("granted", granted))
        if target_granted and expiry_date is not None and expiry_date < now.date():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cannot record granted consent with expiry_date in the past",
            )

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
                expiry_date=expiry_date,
                metadata_json=payload.get("metadata") or {},
                is_minor_or_guardian_managed=is_guardian_managed,
                guardian_relationship=guardian_relationship,
                guardian_identity_reference=payload.get("guardian_identity_reference") if is_guardian_managed else None,
                guardian_verification_method=guardian_verification_method,
                guardian_verified_at=now if is_guardian_managed else None,
                created_at=now,
                updated_at=now,
            )
            self.db.add(row)
            previous_granted = None
        else:
            previous_granted = row.granted
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
            if "is_minor_or_guardian_managed" in payload:
                row.is_minor_or_guardian_managed = is_guardian_managed
                row.guardian_relationship = guardian_relationship
                row.guardian_identity_reference = payload.get("guardian_identity_reference") if is_guardian_managed else None
                row.guardian_verification_method = guardian_verification_method
                row.guardian_verified_at = now if is_guardian_managed else None
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
            metadata_json={"source": "api", "previous_granted": previous_granted},
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

        if not row.granted and row.withdrawn_at is not None:
            return row

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
        expiring_soon_30d = int(
            self.db.execute(
                select(func.count(ConsentRecord.id)).where(
                    *base_filters,
                    ConsentRecord.granted.is_(True),
                    ConsentRecord.expiry_date.is_not(None),
                    ConsentRecord.expiry_date >= today,
                    ConsentRecord.expiry_date <= (today + timedelta(days=30)),
                )
            ).scalar_one()
            or 0
        )
        active_without_notice_count = int(
            self.db.execute(
                select(func.count(ConsentRecord.id)).where(
                    *base_filters,
                    ConsentRecord.granted.is_(True),
                    ConsentRecord.notice_id.is_(None),
                )
            ).scalar_one()
            or 0
        )

        consent_rate = (active_consents / total * 100) if total > 0 else 0.0
        context_flags: list[str] = []
        if expired_count > 0:
            context_flags.append("expired_consents_present")
        if expiring_soon_30d > 0:
            context_flags.append("consents_expiring_within_30_days")
        if active_without_notice_count > 0:
            context_flags.append("active_consents_missing_notice_reference")
        if total > 0 and active_consents == 0:
            context_flags.append("no_active_consents")
        return {
            "total_records": total,
            "active_consents": active_consents,
            "withdrawn_count": withdrawn_count,
            "expired_count": expired_count,
            "consent_rate_pct": round(consent_rate, 2),
            "expiring_soon_30d": expiring_soon_30d,
            "active_without_notice_count": active_without_notice_count,
            "context_flags": context_flags,
        }

    def record_google_consent_mode_v2(
        self,
        org_id: uuid.UUID,
        data,
        actor_user_id: uuid.UUID | None = None,
    ) -> GoogleConsentModeEvent:
        event_timestamp = getattr(data, "event_timestamp", None) if hasattr(data, "event_timestamp") else None
        payload = data.model_dump(mode="json") if hasattr(data, "model_dump") else dict(data)
        subject_identifier = payload.pop("subject_identifier")
        subject_hash = self.hash_subject_identifier(subject_identifier)

        states = {
            "ad_storage": payload["ad_storage"],
            "analytics_storage": payload["analytics_storage"],
            "ad_user_data": payload["ad_user_data"],
            "ad_personalization": payload["ad_personalization"],
        }
        for field, value in states.items():
            validate_choice(value, GCM_V2_STATES, field)

        now = self.utcnow()
        raw_payload = {
            "gcm_version": "v2",
            "domain": payload["domain"],
            "url": payload.get("url"),
            "region": payload.get("region"),
            "client_id": payload.get("client_id"),
            "session_id": payload.get("session_id"),
            "event_name": payload.get("event_name") or "consent_update",
            "event_timestamp": payload.get("event_timestamp"),
            "states": states,
            "metadata": payload.get("metadata") or {},
        }

        row = GoogleConsentModeEvent(
            organization_id=org_id,
            subject_identifier_hash=subject_hash,
            domain=payload["domain"].strip().lower(),
            url=payload.get("url"),
            region=payload.get("region"),
            client_id=payload.get("client_id"),
            session_id=payload.get("session_id"),
            gcm_version="v2",
            event_name=payload.get("event_name") or "consent_update",
            event_timestamp=event_timestamp,
            ad_storage=states["ad_storage"],
            analytics_storage=states["analytics_storage"],
            ad_user_data=states["ad_user_data"],
            ad_personalization=states["ad_personalization"],
            raw_payload_json=raw_payload,
            created_by_user_id=actor_user_id,
            created_at=now,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="consent.google_consent_mode_v2_recorded",
            entity_type="google_consent_mode_event",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={
                "subject_identifier_hash": subject_hash,
                "domain": row.domain,
                "gcm_version": row.gcm_version,
                "states": states,
            },
            metadata_json={"source": "api"},
        )
        return row

    def list_google_consent_mode_v2_events(
        self,
        org_id: uuid.UUID,
        domain: str | None = None,
        subject_identifier: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[GoogleConsentModeEvent]:
        stmt = select(GoogleConsentModeEvent).where(GoogleConsentModeEvent.organization_id == org_id)
        if domain:
            stmt = stmt.where(GoogleConsentModeEvent.domain == domain.strip().lower())
        if subject_identifier:
            stmt = stmt.where(
                GoogleConsentModeEvent.subject_identifier_hash == self.hash_subject_identifier(subject_identifier)
            )
        return self.db.execute(
            stmt.order_by(GoogleConsentModeEvent.created_at.desc()).offset(max(0, int(skip))).limit(max(1, min(int(limit), 500)))
        ).scalars().all()

    def get_google_consent_mode_v2_status(
        self,
        org_id: uuid.UUID,
        domain: str,
        subject_identifier: str,
    ) -> dict:
        """Resolve the *current effective* Consent Mode v2 state for a given
        subject on a given domain, rather than making the caller re-derive it
        from the raw event list. Also surfaces two insights a bare event echo
        would miss: whether the latest known state is stale enough to warrant
        re-prompting, and whether the earliest recorded state for a
        restricted (EEA/UK/Switzerland) region looks inconsistent with
        Google's required denied-by-default posture for those jurisdictions.
        """
        normalized_domain = domain.strip().lower()
        subject_hash = self.hash_subject_identifier(subject_identifier)

        events = self.db.execute(
            select(GoogleConsentModeEvent)
            .where(
                GoogleConsentModeEvent.organization_id == org_id,
                GoogleConsentModeEvent.domain == normalized_domain,
                GoogleConsentModeEvent.subject_identifier_hash == subject_hash,
            )
            .order_by(GoogleConsentModeEvent.created_at.asc())
        ).scalars().all()

        if not events:
            return {
                "has_signal": False,
                "domain": normalized_domain,
                "region": None,
                "ad_storage": None,
                "analytics_storage": None,
                "ad_user_data": None,
                "ad_personalization": None,
                "last_event_at": None,
                "is_stale": False,
                "stale_after_days": GCM_RECONSENT_STALE_DAYS,
                "regional_default_expected": None,
                "default_state_risk": False,
                "default_state_risk_detail": None,
            }

        latest = events[-1]
        earliest = events[0]
        reference_ts = latest.event_timestamp or latest.created_at
        if reference_ts is not None and reference_ts.tzinfo is None:
            reference_ts = reference_ts.replace(tzinfo=UTC)
        now = self.utcnow()
        age_days = (now - reference_ts).days if reference_ts else None
        is_stale = age_days is not None and age_days > GCM_RECONSENT_STALE_DAYS

        region_flag = _is_restricted_default_region(latest.region)
        regional_default_expected = None
        if region_flag is True:
            regional_default_expected = "denied"
        elif region_flag is False:
            regional_default_expected = "granted"

        default_state_risk = False
        default_state_risk_detail = None
        earliest_region_flag = _is_restricted_default_region(earliest.region)
        if earliest_region_flag is True:
            granted_signals = [
                name
                for name in ("ad_storage", "analytics_storage", "ad_user_data", "ad_personalization")
                if getattr(earliest, name) == "granted"
            ]
            if granted_signals:
                default_state_risk = True
                default_state_risk_detail = (
                    f"Earliest recorded Consent Mode v2 state for this subject in a "
                    f"restricted region ({earliest.region}) already shows "
                    f"{', '.join(granted_signals)} as granted. Google requires these "
                    "signals to default to 'denied' in the EEA/UK/Switzerland until "
                    "the visitor interacts with a consent banner — verify the tag "
                    "default configuration for this domain."
                )

        return {
            "has_signal": True,
            "domain": normalized_domain,
            "region": latest.region,
            "ad_storage": latest.ad_storage,
            "analytics_storage": latest.analytics_storage,
            "ad_user_data": latest.ad_user_data,
            "ad_personalization": latest.ad_personalization,
            "last_event_at": reference_ts,
            "is_stale": is_stale,
            "stale_after_days": GCM_RECONSENT_STALE_DAYS,
            "regional_default_expected": regional_default_expected,
            "default_state_risk": default_state_risk,
            "default_state_risk_detail": default_state_risk_detail,
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
        return SubsystemIngestKeyService(self.db).require_org_by_key(raw_key, "consent")

    def receive_inbound_event(self, raw_key: str, payload) -> ConsentRecord:
        org_id = self.resolve_org_by_api_key(raw_key)
        event_payload = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
        activity_id = event_payload["processing_activity_id"]
        return self.record_consent(org_id, activity_id, event_payload, granted=bool(event_payload.get("granted", True)), actor_user_id=None)


def run_daily_consent_expiry_sweep(db: Session) -> dict:
    return ConsentService(db).sweep_expired_consents()
