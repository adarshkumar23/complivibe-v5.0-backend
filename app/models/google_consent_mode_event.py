import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class GoogleConsentModeEvent(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "google_consent_mode_events"
    __table_args__ = (
        CheckConstraint("ad_storage IN ('granted', 'denied')", name="ck_gcm_ad_storage"),
        CheckConstraint("analytics_storage IN ('granted', 'denied')", name="ck_gcm_analytics_storage"),
        CheckConstraint("ad_user_data IN ('granted', 'denied')", name="ck_gcm_ad_user_data"),
        CheckConstraint("ad_personalization IN ('granted', 'denied')", name="ck_gcm_ad_personalization"),
        Index("ix_gcm_events_org_created", "organization_id", "created_at"),
        Index("ix_gcm_events_org_domain", "organization_id", "domain"),
        Index("ix_gcm_events_org_subject_hash", "organization_id", "subject_identifier_hash"),
    )

    subject_identifier_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    region: Mapped[str | None] = mapped_column(String(50), nullable=True)
    client_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gcm_version: Mapped[str] = mapped_column(String(20), nullable=False, default="v2")
    event_name: Mapped[str] = mapped_column(String(100), nullable=False, default="consent_update")
    event_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ad_storage: Mapped[str] = mapped_column(String(20), nullable=False)
    analytics_storage: Mapped[str] = mapped_column(String(20), nullable=False)
    ad_user_data: Mapped[str] = mapped_column(String(20), nullable=False)
    ad_personalization: Mapped[str] = mapped_column(String(20), nullable=False)
    raw_payload_json: Mapped[dict] = mapped_column("raw_payload", JSON, nullable=False, default=dict)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
