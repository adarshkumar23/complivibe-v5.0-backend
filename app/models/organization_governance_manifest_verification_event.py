import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class OrganizationGovernanceManifestVerificationEvent(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "organization_governance_manifest_verification_events"
    __table_args__ = (
        Index(
            "ix_org_governance_manifest_verification_events_org_manifest_verified",
            "organization_id",
            "manifest_id",
            "verified_at",
        ),
        Index(
            "ix_org_governance_manifest_verification_events_org_trusted_verified",
            "organization_id",
            "trusted",
            "verified_at",
        ),
    )

    manifest_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organization_governance_evidence_manifests.id", ondelete="CASCADE"),
        nullable=False,
    )
    verified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_hash: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    valid_signature: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    trusted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    key_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    key_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    legacy_verification: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    recomputed_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    signature_algorithm: Mapped[str] = mapped_column(String(32), nullable=False)
    verification_result_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    caveat: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
