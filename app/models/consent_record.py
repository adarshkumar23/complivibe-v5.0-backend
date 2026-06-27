import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class ConsentRecord(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "consent_records"
    __table_args__ = (
        CheckConstraint(
            "consent_mechanism IN ('explicit_checkbox', 'cookie_banner', 'written_form', 'verbal_recorded', 'api_consent', 'implied')",
            name="ck_consent_records_mechanism",
        ),
        Index("ix_consent_records_org_activity", "organization_id", "processing_activity_id"),
        Index("ix_consent_records_org_subject_hash", "organization_id", "subject_identifier_hash"),
        Index("ix_consent_records_org_granted_activity", "organization_id", "granted", "processing_activity_id"),
        Index("ix_consent_records_expiry_granted", "expiry_date", "granted"),
    )

    processing_activity_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("processing_activities.id", ondelete="CASCADE"), nullable=False)
    notice_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("privacy_notices.id", ondelete="SET NULL"), nullable=True)
    subject_identifier: Mapped[str] = mapped_column(String(500), nullable=False)
    subject_identifier_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    consent_mechanism: Mapped[str] = mapped_column(String(50), nullable=False)
    consent_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    withdrawal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
