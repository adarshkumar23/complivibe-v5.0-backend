import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ContentProvenanceRecord(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    """Stores the outcome of validating a submitted content-provenance manifest.

    Records are an audit trail of verification attempts and are not deleted in
    the normal course of business; ``deleted_at`` is included only for the
    house soft-delete convention, not as an expected operational path.
    """

    __tablename__ = "content_provenance_records"
    __table_args__ = (
        CheckConstraint(
            "verification_status IN ('valid', 'invalid')",
            name="ck_content_provenance_records_verification_status",
        ),
        CheckConstraint(
            "invalid_reason IN ('missing_signature', 'malformed_claim', 'unsupported_version', 'tampered_signature')"
            " OR invalid_reason IS NULL",
            name="ck_content_provenance_records_invalid_reason",
        ),
        Index("ix_content_provenance_records_org_status", "organization_id", "verification_status"),
        Index("ix_content_provenance_records_org_identifier", "organization_id", "content_identifier"),
    )

    content_identifier: Mapped[str] = mapped_column(String(500), nullable=False)
    raw_manifest: Mapped[dict] = mapped_column(JSON, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(20), nullable=False)
    invalid_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    spec_version_detected: Mapped[str | None] = mapped_column(String(100), nullable=True)
    claim_generator: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assertion_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
