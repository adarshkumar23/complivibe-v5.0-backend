import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class ExportAttestation(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "export_attestations"
    __table_args__ = (
        Index("ix_export_attestations_org_export", "organization_id", "export_job_id"),
        Index("ix_export_attestations_org_status", "organization_id", "status"),
        Index("ix_export_attestations_export_attested", "export_job_id", "attested_at"),
    )

    export_job_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("export_jobs.id", ondelete="CASCADE"), nullable=False)
    attestation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    attested_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    attested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    export_checksum_sha256: Mapped[str] = mapped_column(String(128), nullable=False)
    export_integrity_signature: Mapped[str | None] = mapped_column(String(256), nullable=True)
    attestation_checksum_sha256: Mapped[str] = mapped_column(String(128), nullable=False)
    attestation_signature: Mapped[str | None] = mapped_column(String(256), nullable=True)
    signing_key_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    signature_algorithm: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
