import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin

CONNECTOR_TYPES = ("aws", "gcp", "azure", "okta", "github")


class CloudEvidenceConnector(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    """A per-org, agent-push evidence connector instance for a cloud/SaaS provider.
    CompliVibe never initiates an outbound scan/call against the customer's environment —
    the customer configures their own provider's native push mechanism (EventBridge,
    Pub/Sub push subscription, Event Grid, Event Hooks, webhooks) to send findings here."""

    __tablename__ = "cloud_evidence_connectors"
    __table_args__ = (
        CheckConstraint("connector_type IN ('aws', 'gcp', 'azure', 'okta', 'github')", name="ck_cloud_connectors_type"),
        CheckConstraint(
            "status IN ('unconfigured', 'active', 'disabled', 'error')", name="ck_cloud_connectors_status"
        ),
        UniqueConstraint("webhook_token", name="uq_cloud_connectors_webhook_token"),
        Index("ix_cloud_connectors_org_type", "organization_id", "connector_type"),
        Index("ix_cloud_connectors_org_status", "organization_id", "status"),
    )

    connector_type: Mapped[str] = mapped_column(String(20), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unconfigured")
    webhook_token: Mapped[str] = mapped_column(String(64), nullable=False)
    # Vault-encrypted via SecretsService; meaning is provider-specific (HMAC key for
    # AWS/GitHub, shared header value for Azure/Okta, unused for GCP which uses
    # Google-signed OIDC bearer tokens instead of a shared secret).
    signing_secret_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    secret_revealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    auto_apply_deterministic_mappings: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expected_event_interval_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    last_event_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class CloudEvidenceConnectorEvent(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    """Idempotency + audit trail for each inbound provider event, mirroring
    EvidenceAutomationIngestEvent's dedup shape."""

    __tablename__ = "cloud_evidence_connector_events"
    __table_args__ = (
        CheckConstraint("status IN ('created', 'duplicate', 'error')", name="ck_cloud_connector_events_status"),
        UniqueConstraint("connector_id", "provider_event_id", name="uq_cloud_connector_events_dedup"),
        Index("ix_cloud_connector_events_org_connector", "organization_id", "connector_id"),
    )

    connector_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("cloud_evidence_connectors.id", ondelete="CASCADE"), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence_item_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("evidence_items.id", ondelete="SET NULL"), nullable=True)
    finding_summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
