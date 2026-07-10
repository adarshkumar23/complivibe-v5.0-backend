import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class DataSubjectRequest(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "data_subject_requests"
    __table_args__ = (
        CheckConstraint(
            "request_type IN ('access', 'erasure', 'portability', 'rectification', 'restriction', 'objection', 'opt_out_of_sale', 'limit_sensitive', 'know', 'correct')",
            name="ck_data_subject_requests_request_type",
        ),
        CheckConstraint(
            "status IN ('received', 'identity_verification', 'in_progress', 'on_hold', 'fulfilled', 'refused', 'partially_fulfilled', 'withdrawn')",
            name="ck_data_subject_requests_status",
        ),
        CheckConstraint(
            "regulatory_framework IN ('gdpr', 'ccpa', 'dpdp', 'lgpd', 'custom')",
            name="ck_data_subject_requests_framework",
        ),
        CheckConstraint(
            "request_subtype IS NULL OR request_subtype IN ('rights_request', 'grievance')",
            name="ck_dsr_request_subtype",
        ),
        Index("ix_data_subject_requests_org_status", "organization_id", "status"),
        Index("ix_data_subject_requests_org_type", "organization_id", "request_type"),
        Index("ix_data_subject_requests_org_deadline", "organization_id", "response_deadline"),
        Index("ix_data_subject_requests_org_subject_email", "organization_id", "subject_email"),
        UniqueConstraint("organization_id", "request_ref", name="uq_data_subject_requests_org_ref"),
    )

    request_ref: Mapped[str] = mapped_column(String(50), nullable=False)
    request_type: Mapped[str] = mapped_column(String(30), nullable=False)
    subject_name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject_email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject_identifier: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="received")
    regulatory_framework: Mapped[str] = mapped_column(String(20), nullable=False, default="gdpr")
    response_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deadline_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    extension_granted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    extension_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extension_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    identity_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    identity_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    identity_verified_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assigned_handler_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    response_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    refusal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # DPDP Rules 2025 Rule 14(3): grievances get a distinct 90-day SLA ceiling, separate
    # from the general rights-request deadline.
    request_subtype: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Data categories this request touches (e.g. "kyc_identity_documents",
    # "transaction_records"), used to look up legal-retention conflicts before erasure.
    data_categories: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    retention_conflict_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    retention_conflict_overridden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retention_conflict_override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # DPDP Act 2023 Section 10: a nominee with an activated nomination may submit rights
    # requests on the Data Principal's behalf.
    submitted_by_nominee_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("data_principal_nominations.id", ondelete="SET NULL"), nullable=True
    )
    # Anchor date (e.g. account/relationship closure) the RBI-DPDP reconciliation engine
    # needs to compute an exact retention-floor expiry for this request's data categories.
    relationship_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
