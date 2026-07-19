"""Signature-scored shadow-AI detection, decay, IdP scan and federated pooling.

This is the graft of the shadow-ai-discovery-engine patent repo. It runs
alongside -- never instead of -- core's existing shadow-AI feature in
``app/ai_governance/services/shadow_ai_service.py``, which this module does not
import, mutate, or read.

Reconciliation applied during the port:

* All AuditService calls use core's real frozen instance signature
  ``AuditService(db).write_audit_log(*, action, entity_type, organization_id,
  actor_user_id, ...)``. Upstream called a ``AuditService.log(db, ...)``
  staticmethod that does not exist here.
* Every query is filtered on ``organization_id``; the upstream service relied on
  an always-allow permission stub and did not consistently scope reads.
* Promotion targets core's real ``ai_systems`` inventory rather than the
  upstream repo's private ``ai_systems`` stub table (whose NOT NULL unique
  ``source_detection_id`` could never retrofit core's populated table).
"""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.ai_governance.services.shadow_ai_signature.confidence_engine import (
    ShadowAIConfidenceEngine,
)
from app.models.shadow_ai_signature import (
    ShadowAIFederatedObservation,
    ShadowAIFederatedSubmission,
    ShadowAIIdpConnection,
    ShadowAIIdpSyncLog,
    ShadowAISignatureDetection,
    ShadowAISignatureRegistry,
    ShadowAISuppressedDetection,
    ShadowAITelemetryEvent,
)
from app.services.audit_service import AuditService

# Distinct-tenant threshold before a federated hostname becomes a candidate.
# Two tenants is the minimum that can distinguish "emerging provider" from
# "one noisy customer", which is the entire point of pooling.
FEDERATED_CANDIDATE_MIN_ORGS = 2

# Salt namespace for federated hostname hashing. Hostnames are pooled across
# tenants, so only the hash crosses the boundary.
_FEDERATED_HASH_NAMESPACE = "complivibe.shadow_ai.federated"

# Confidence half-life: a detection with no new signal decays toward zero.
DEFAULT_DECAY_LAMBDA = Decimal("0.05")
STALE_BELOW_SCORE = Decimal("0.40")


class ShadowAISignatureService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    # ------------------------------------------------------------------
    # Telemetry ingest (tiers 1-3)
    # ------------------------------------------------------------------
    def ingest_telemetry(
        self,
        *,
        organization_id: uuid.UUID,
        tier: int,
        event_type: str,
        raw_signal: dict,
        source_system_label: str | None,
        matched_signature_id: uuid.UUID | None,
        observed_at: datetime | None = None,
    ) -> tuple[ShadowAITelemetryEvent | None, bool]:
        """Store one telemetry signal. Returns (event, was_duplicate).

        Deduplication uses the patent-invariant signal hash, enforced by a
        unique constraint so concurrent ingests cannot both win.
        """
        observed = observed_at or self.utcnow()
        signal_hash = ShadowAIConfidenceEngine.compute_signal_hash(
            organization_id,
            matched_signature_id or uuid.UUID(int=0),
            source_system_label or "",
            observed.date(),
        )

        existing = self.db.execute(
            select(ShadowAITelemetryEvent).where(
                ShadowAITelemetryEvent.organization_id == organization_id,
                ShadowAITelemetryEvent.signal_hash == signal_hash,
            )
        ).scalars().first()
        if existing is not None:
            return existing, True

        event = ShadowAITelemetryEvent(
            organization_id=organization_id,
            tier=tier,
            event_type=event_type,
            source_system_label=source_system_label,
            matched_signature_id=matched_signature_id,
            raw_signal_json=json.dumps(raw_signal),
            signal_hash=signal_hash,
            observed_at=observed,
            ingested_at=self.utcnow(),
        )
        self.db.add(event)
        self.db.flush()
        return event, False

    # ------------------------------------------------------------------
    # Scoring / detection upsert
    # ------------------------------------------------------------------
    def recompute_detections(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None = None,
    ) -> dict[str, int]:
        """Rescore every signature that has telemetry for this org.

        Applies the patent band rule: a DISCARD score (<0.40) must not create a
        detection record.
        """
        created = updated = discarded = suppressed_skipped = 0

        suppressed_ids = {
            row.signature_id
            for row in self.db.execute(
                select(ShadowAISuppressedDetection).where(
                    ShadowAISuppressedDetection.organization_id == organization_id
                )
            ).scalars().all()
        }

        signature_ids = [
            row
            for row in self.db.execute(
                select(ShadowAITelemetryEvent.matched_signature_id)
                .where(
                    ShadowAITelemetryEvent.organization_id == organization_id,
                    ShadowAITelemetryEvent.matched_signature_id.isnot(None),
                )
                .distinct()
            ).scalars().all()
        ]

        for signature_id in signature_ids:
            if signature_id in suppressed_ids:
                suppressed_skipped += 1
                continue

            signature = self.db.get(ShadowAISignatureRegistry, signature_id)
            if signature is None or not signature.is_active:
                continue

            events = self.db.execute(
                select(ShadowAITelemetryEvent).where(
                    ShadowAITelemetryEvent.organization_id == organization_id,
                    ShadowAITelemetryEvent.matched_signature_id == signature_id,
                )
            ).scalars().all()

            score, breakdown = ShadowAIConfidenceEngine.compute_score(signature, list(events))
            band = ShadowAIConfidenceEngine.classify_confidence_band(score)

            existing = self.db.execute(
                select(ShadowAISignatureDetection).where(
                    ShadowAISignatureDetection.organization_id == organization_id,
                    ShadowAISignatureDetection.signature_id == signature_id,
                )
            ).scalars().first()

            if band == "discard":
                discarded += 1
                continue

            first_seen = min(e.observed_at for e in events)
            last_seen = max(e.observed_at for e in events)

            if existing is None:
                detection = ShadowAISignatureDetection(
                    organization_id=organization_id,
                    signature_id=signature_id,
                    provider_name=signature.provider_name,
                    confidence_score=Decimal(str(score)),
                    base_confidence_score=Decimal(str(score)),
                    confidence_band=band,
                    detection_basis_json=json.dumps(breakdown),
                    event_count=len(events),
                    status="new",
                    first_detected_at=first_seen,
                    last_observed_at=last_seen,
                    is_stale=False,
                )
                self.db.add(detection)
                self.db.flush()
                created += 1
                AuditService(self.db).write_audit_log(
                    action="shadow_ai_signature.detection_created",
                    entity_type="shadow_ai_signature_detection",
                    entity_id=detection.id,
                    organization_id=organization_id,
                    actor_user_id=actor_user_id,
                    after_json={
                        "provider_name": signature.provider_name,
                        "confidence_score": float(score),
                        "confidence_band": band,
                    },
                    metadata_json={"source": "shadow_ai_signature_scan"},
                )
            else:
                existing.confidence_score = Decimal(str(score))
                existing.base_confidence_score = Decimal(str(score))
                existing.confidence_band = band
                existing.detection_basis_json = json.dumps(breakdown)
                existing.event_count = len(events)
                existing.last_observed_at = last_seen
                existing.is_stale = False
                existing.decayed_at = None
                updated += 1

        return {
            "created": created,
            "updated": updated,
            "discarded": discarded,
            "suppressed_skipped": suppressed_skipped,
            "records_processed": created + updated,
        }

    # ------------------------------------------------------------------
    # Decay tracking
    # ------------------------------------------------------------------
    def apply_decay(
        self,
        *,
        organization_id: uuid.UUID,
        as_of: datetime | None = None,
    ) -> dict[str, int]:
        """Age confidence for detections with no recent observation.

        score = base * exp(-lambda * days_since_last_observation)

        A detection whose decayed score falls below the MEDIUM band floor is
        marked stale rather than deleted, so the evidence trail survives.
        """
        now = as_of or self.utcnow()
        decayed = marked_stale = 0

        rows = self.db.execute(
            select(ShadowAISignatureDetection).where(
                ShadowAISignatureDetection.organization_id == organization_id,
                ShadowAISignatureDetection.status.notin_(["dismissed", "registered"]),
            )
        ).scalars().all()

        for row in rows:
            base = row.base_confidence_score or row.confidence_score
            lam = row.decay_lambda or DEFAULT_DECAY_LAMBDA
            days = max(0.0, (now - row.last_observed_at).total_seconds() / 86400.0)
            if days <= 0:
                continue
            factor = math.exp(-float(lam) * days)
            new_score = (Decimal(str(round(float(base) * factor, 4)))).quantize(Decimal("0.0001"))
            if new_score == row.confidence_score:
                continue
            row.confidence_score = new_score
            row.decayed_at = now
            decayed += 1
            if new_score < STALE_BELOW_SCORE and not row.is_stale:
                row.is_stale = True
                marked_stale += 1

        return {"decayed": decayed, "marked_stale": marked_stale, "records_processed": decayed}

    # ------------------------------------------------------------------
    # Triage
    # ------------------------------------------------------------------
    def review_detection(
        self,
        *,
        organization_id: uuid.UUID,
        detection_id: uuid.UUID,
        new_status: str,
        actor_user_id: uuid.UUID,
        reason: str | None = None,
    ) -> ShadowAISignatureDetection | None:
        detection = self.db.execute(
            select(ShadowAISignatureDetection).where(
                ShadowAISignatureDetection.id == detection_id,
                ShadowAISignatureDetection.organization_id == organization_id,
            )
        ).scalars().first()
        if detection is None:
            return None

        before = {"status": detection.status}
        detection.status = new_status
        detection.reviewed_by_user_id = actor_user_id
        detection.reviewed_at = self.utcnow()
        if new_status == "dismissed":
            detection.dismissal_reason = reason

        AuditService(self.db).write_audit_log(
            action=f"shadow_ai_signature.detection_{new_status}",
            entity_type="shadow_ai_signature_detection",
            entity_id=detection.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json={"status": new_status, "reason": reason},
            metadata_json={"source": "api"},
        )
        return detection

    def suppress_signature(
        self,
        *,
        organization_id: uuid.UUID,
        signature_id: uuid.UUID,
        reason: str,
        actor_user_id: uuid.UUID,
    ) -> ShadowAISuppressedDetection:
        row = ShadowAISuppressedDetection(
            organization_id=organization_id,
            signature_id=signature_id,
            reason=reason,
            suppressed_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="shadow_ai_signature.suppressed",
            entity_type="shadow_ai_suppressed_detection",
            entity_id=row.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            after_json={"signature_id": str(signature_id), "reason": reason},
            metadata_json={"source": "api"},
        )
        return row

    # ------------------------------------------------------------------
    # IdP scan (tier 2)
    # ------------------------------------------------------------------
    def record_idp_scan(
        self,
        *,
        organization_id: uuid.UUID,
        connection_id: uuid.UUID,
        oauth_grants: list[dict],
        actor_user_id: uuid.UUID | None = None,
    ) -> dict[str, int]:
        """Match OAuth grants against signatures and emit tier-2 telemetry."""
        connection = self.db.execute(
            select(ShadowAIIdpConnection).where(
                ShadowAIIdpConnection.id == connection_id,
                ShadowAIIdpConnection.organization_id == organization_id,
                ShadowAIIdpConnection.deleted_at.is_(None),
            )
        ).scalars().first()
        if connection is None:
            return {"error": "connection_not_found"}

        started = self.utcnow()
        signatures = self.db.execute(
            select(ShadowAISignatureRegistry).where(ShadowAISignatureRegistry.is_active.is_(True))
        ).scalars().all()

        fetched = len(oauth_grants)
        matched = created = duplicate = 0

        for grant in oauth_grants:
            app_name = (grant.get("app_name") or "").lower()
            app_id = (grant.get("app_id") or "").lower()
            signature_id = None
            for sig in signatures:
                patterns = [p.lower() for p in json.loads(sig.oauth_app_patterns)]
                if app_name in patterns or app_id in patterns:
                    signature_id = sig.id
                    break
            if signature_id is None:
                continue

            matched += 1
            _, was_dup = self.ingest_telemetry(
                organization_id=organization_id,
                tier=2,
                event_type="identity_match",
                raw_signal=grant,
                source_system_label=connection.idp_provider,
                matched_signature_id=signature_id,
            )
            if was_dup:
                duplicate += 1
            else:
                created += 1

        log = ShadowAIIdpSyncLog(
            organization_id=organization_id,
            connection_id=connection_id,
            idp_provider=connection.idp_provider,
            events_fetched=fetched,
            events_matched=matched,
            signals_created=created,
            signals_duplicate=duplicate,
            started_at=started,
            completed_at=self.utcnow(),
        )
        self.db.add(log)
        connection.last_synced_at = self.utcnow()
        connection.sync_status = "ok"
        connection.total_syncs += 1
        connection.total_signals += created
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="shadow_ai_signature.idp_scanned",
            entity_type="shadow_ai_idp_connection",
            entity_id=connection_id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            after_json={"fetched": fetched, "matched": matched, "created": created},
            metadata_json={"source": "idp_scan"},
        )
        return {
            "events_fetched": fetched,
            "events_matched": matched,
            "signals_created": created,
            "signals_duplicate": duplicate,
        }

    # ------------------------------------------------------------------
    # Federated detection
    # ------------------------------------------------------------------
    @staticmethod
    def hash_hostname(hostname: str) -> str:
        return hashlib.sha256(f"{_FEDERATED_HASH_NAMESPACE}:{hostname.lower()}".encode()).hexdigest()

    def submit_federated_observation(
        self,
        *,
        organization_id: uuid.UUID,
        hostname: str,
        behavioral_score: float | None = None,
    ) -> dict:
        """Contribute a hostname sighting to the cross-tenant pool.

        Only the salted hash is pooled. ``observation_count`` counts *distinct
        submitting tenants*, enforced by the unique (org, hash) constraint, so a
        single noisy tenant cannot promote a hostname by itself.
        """
        now = self.utcnow()
        hostname_hash = self.hash_hostname(hostname)

        # Atomic: concurrent tenants must not both be treated as first.
        # RETURNING is required here -- psycopg reports rowcount == -1 for
        # INSERT ... ON CONFLICT DO NOTHING, so a rowcount test silently treats
        # every submission as a duplicate and the distinct-org count never moves.
        stmt = (
            pg_insert(ShadowAIFederatedSubmission)
            .values(
                id=uuid.uuid4(),
                organization_id=organization_id,
                hostname_hash=hostname_hash,
                submitted_at=now,
                behavioral_score=Decimal(str(behavioral_score)) if behavioral_score is not None else None,
                was_duplicate=False,
            )
            .on_conflict_do_nothing(constraint="uq_shadow_ai_federated_sub_org_hash")
            .returning(ShadowAIFederatedSubmission.id)
        )
        is_new_for_org = self.db.execute(stmt).scalar() is not None

        observation = self.db.execute(
            select(ShadowAIFederatedObservation).where(
                ShadowAIFederatedObservation.hostname_hash == hostname_hash
            )
        ).scalars().first()

        if observation is None:
            observation = ShadowAIFederatedObservation(
                hostname_hash=hostname_hash,
                hostname=hostname,
                observation_count=1 if is_new_for_org else 0,
                first_observed_at=now,
                last_observed_at=now,
                behavioral_score=Decimal(str(behavioral_score)) if behavioral_score is not None else None,
                status="observed",
            )
            self.db.add(observation)
        else:
            observation.last_observed_at = now
            if is_new_for_org:
                observation.observation_count += 1

        if (
            observation.observation_count >= FEDERATED_CANDIDATE_MIN_ORGS
            and observation.status == "observed"
        ):
            observation.status = "candidate"

        self.db.flush()
        return {
            "hostname_hash": hostname_hash,
            "distinct_orgs": observation.observation_count,
            "status": observation.status,
            "was_duplicate": not is_new_for_org,
        }
