"""Signature-scored shadow-AI discovery (patent: shadow-ai-discovery-engine).

GRAFT, NOT REPLACEMENT. Core already ships a live shadow-AI feature
(``shadow_ai_detections`` + ``app/ai_governance/services/shadow_ai_service.py``),
which is untouched by this module. That feature records human/scanner-reported
sightings with a coarse ``confidence`` string. This one infers *undeclared* AI
systems from enterprise telemetry and scores them with a weighted multi-signal
algorithm.

Every table here is namespaced ``shadow_ai_*`` so ownership is unambiguous and
no future core table can collide. In particular the upstream repo's
``shadow_ai_detections`` is renamed ``shadow_ai_signature_detections``: the
upstream schema (provider_name / confidence_band / signature_id) is
incompatible with core's live table of the same name, and both must coexist.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ShadowAISignatureRegistry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Global catalogue of known AI providers and how to recognise them.

    Deliberately NOT organization-owned: signatures are platform reference data,
    like the frameworks/obligations catalogue. ``confidence_weights`` supplies
    the per-signal weights consumed by the patent scoring algorithm.
    """

    __tablename__ = "shadow_ai_signature_registry"
    __table_args__ = (
        CheckConstraint(
            "risk_level IN ('low', 'medium', 'high', 'critical')",
            name="ck_shadow_ai_sig_registry_risk_level",
        ),
        Index("ix_shadow_ai_sig_registry_active", "is_active"),
    )

    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    provider_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    # JSON-encoded lists/objects, stored as Text to match the upstream patent
    # implementation byte-for-byte (the scoring algorithm json.loads() these).
    endpoint_patterns: Mapped[str] = mapped_column(Text, nullable=False)
    keyword_patterns: Mapped[str] = mapped_column(Text, nullable=False)
    oauth_app_patterns: Mapped[str] = mapped_column(Text, nullable=False)
    data_egress_indicators: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_weights: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ShadowAITelemetryEvent(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    """A single observed signal, from any of the three detection tiers.

    tier 1 = questionnaire text, 2 = identity-provider OAuth logs,
    3 = network/API edge. ``signal_hash`` deduplicates a signal across scans and
    is a patent invariant (see ShadowAIConfidenceEngine.compute_signal_hash).
    """

    __tablename__ = "shadow_ai_telemetry_events"
    __table_args__ = (
        CheckConstraint("tier IN (1, 2, 3)", name="ck_shadow_ai_telemetry_tier"),
        UniqueConstraint("organization_id", "signal_hash", name="uq_shadow_ai_telemetry_org_hash"),
        Index("ix_shadow_ai_telemetry_org_signature", "organization_id", "matched_signature_id"),
        Index("ix_shadow_ai_telemetry_observed_at", "observed_at"),
    )

    tier: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_system_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    matched_signature_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("shadow_ai_signature_registry.id", ondelete="SET NULL"), nullable=True
    )
    raw_signal_json: Mapped[str] = mapped_column(Text, nullable=False)
    signal_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ShadowAISignatureDetection(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    """An inferred undeclared AI system, scored from aggregated telemetry.

    Renamed from the upstream ``shadow_ai_detections`` because core already owns
    that table name with an incompatible schema. ``registered_ai_system_id``
    points at core's real ``ai_systems`` table rather than the upstream repo's
    stub, so promotion lands in the inventory users already use.
    """

    __tablename__ = "shadow_ai_signature_detections"
    __table_args__ = (
        CheckConstraint(
            "confidence_band IN ('high', 'medium')",
            name="ck_shadow_ai_sig_detections_band",
        ),
        CheckConstraint(
            "status IN ('new', 'under_review', 'confirmed', 'dismissed', 'escalated', 'registered')",
            name="ck_shadow_ai_sig_detections_status",
        ),
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_shadow_ai_sig_detections_score_range",
        ),
        UniqueConstraint(
            "organization_id", "signature_id", name="uq_shadow_ai_sig_detections_org_signature"
        ),
        Index("ix_shadow_ai_sig_detections_org_status", "organization_id", "status"),
        Index("ix_shadow_ai_sig_detections_stale", "organization_id", "is_stale"),
    )

    signature_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shadow_ai_signature_registry.id", ondelete="CASCADE"), nullable=False
    )
    provider_name: Mapped[str] = mapped_column(String(255), nullable=False)
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    confidence_band: Mapped[str] = mapped_column(String(10), nullable=False)
    detection_basis_json: Mapped[str] = mapped_column(Text, nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new")
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Promotion target is core's real ai_systems inventory, not a private stub.
    registered_ai_system_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_systems.id", ondelete="SET NULL"), nullable=True
    )

    # Decay tracking: confidence ages out when a provider stops being observed.
    base_confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    decay_lambda: Mapped[Decimal | None] = mapped_column(Numeric(6, 5), nullable=True)
    decayed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ShadowAISuppressedDetection(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    """An org-level suppression rule: never re-raise this provider."""

    __tablename__ = "shadow_ai_suppressed_detections"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "signature_id", name="uq_shadow_ai_suppressed_org_signature"
        ),
    )

    signature_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shadow_ai_signature_registry.id", ondelete="CASCADE"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    suppressed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class ShadowAIIdpConnection(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, TimestampMixin, Base):
    """An identity-provider connection scanned for AI OAuth grants (tier 2).

    Tokens are stored encrypted, following the same convention as core's other
    credential-holding integrations.
    """

    __tablename__ = "shadow_ai_idp_connections"
    __table_args__ = (
        CheckConstraint(
            "idp_provider IN ('okta', 'azure_ad', 'google_workspace')",
            name="ck_shadow_ai_idp_provider",
        ),
        CheckConstraint(
            "sync_status IN ('pending', 'syncing', 'ok', 'error')",
            name="ck_shadow_ai_idp_sync_status",
        ),
        Index("ix_shadow_ai_idp_org_provider", "organization_id", "idp_provider"),
    )

    idp_provider: Mapped[str] = mapped_column(String(30), nullable=False)
    access_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idp_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scopes_granted: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sync_window_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    total_syncs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_signals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    connected_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ShadowAIIdpSyncLog(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    """Per-run record of an IdP scan, for observability and dedup accounting."""

    __tablename__ = "shadow_ai_idp_sync_logs"
    __table_args__ = (
        Index("ix_shadow_ai_idp_sync_logs_connection", "connection_id"),
    )

    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shadow_ai_idp_connections.id", ondelete="CASCADE"), nullable=False
    )
    idp_provider: Mapped[str] = mapped_column(String(30), nullable=False)
    events_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    events_matched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    signals_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    signals_duplicate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ShadowAIFederatedObservation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Cross-tenant hostname observation used to surface emerging AI providers.

    Deliberately NOT organization-owned: the whole point is aggregation across
    tenants. Only a salted hostname *hash* plus counts are held here; the
    per-tenant submission trail lives in ShadowAIFederatedSubmission.
    """

    __tablename__ = "shadow_ai_federated_observations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('observed', 'candidate', 'promoted', 'rejected')",
            name="ck_shadow_ai_federated_status",
        ),
        UniqueConstraint("hostname_hash", name="uq_shadow_ai_federated_hostname_hash"),
        Index("ix_shadow_ai_federated_status", "status"),
    )

    hostname_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hostname: Mapped[str] = mapped_column(String(500), nullable=False)
    # Distinct submitting orgs, not raw hits -- one noisy tenant must not promote
    # a hostname on its own.
    observation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    behavioral_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="observed")
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promoted_signature_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("shadow_ai_signature_registry.id", ondelete="SET NULL"), nullable=True
    )


class ShadowAIFederatedSubmission(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    """Which tenant contributed which hostname hash, once per (org, hash).

    The unique constraint is what makes ``observation_count`` a distinct-tenant
    count rather than a hit count.
    """

    __tablename__ = "shadow_ai_federated_submissions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "hostname_hash", name="uq_shadow_ai_federated_sub_org_hash"
        ),
    )

    hostname_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    behavioral_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    was_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
