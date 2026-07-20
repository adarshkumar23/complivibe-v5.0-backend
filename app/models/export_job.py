import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ExportJob(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "export_jobs"
    __table_args__ = (
        Index("ix_export_jobs_org_type", "organization_id", "export_type"),
        Index("ix_export_jobs_org_status", "organization_id", "status"),
        Index("ix_export_jobs_org_framework", "organization_id", "framework_id"),
        Index("ix_export_jobs_org_completed", "organization_id", "completed_at"),
    )

    export_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_report_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("compliance_reports.id", ondelete="SET NULL"),
        nullable=True,
    )
    framework_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("frameworks.id", ondelete="SET NULL"),
        nullable=True,
    )
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    package_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    manifest_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    provenance_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(128), nullable=True)
    integrity_signature: Mapped[str | None] = mapped_column(String(256), nullable=True)
    signing_key_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    signature_algorithm: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Signature validity window. Both are embedded in the signed payload (see
    # ExportService.compute_integrity_signature), so tampering with the stored window
    # invalidates the signature. Nullable: exports signed before this window existed
    # have no expiry and verify under the legacy (window-less) signature.
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    not_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    legal_hold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    legal_hold_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    legal_hold_set_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    legal_hold_set_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attestation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unattested")
    latest_attestation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("export_attestations.id", ondelete="SET NULL", use_alter=True, name="fk_export_jobs_latest_attestation_id"),
        nullable=True,
    )
    package_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0")
    immutable_after_completion: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
