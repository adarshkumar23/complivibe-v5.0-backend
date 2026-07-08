import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AttestationToken(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "attestation_tokens"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'revoked', 'expired')",
            name="ck_attestation_tokens_status",
        ),
        Index("ix_attestation_tokens_token_hash", "token_hash"),
        Index("ix_attestation_tokens_org_status", "organization_id", "status"),
        Index("ix_attestation_tokens_org_purpose", "organization_id", "purpose"),
        Index("ix_attestation_tokens_org_entity", "organization_id", "linked_entity_type", "linked_entity_id"),
    )

    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    scope_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    linked_entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    linked_entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    validation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    revocation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
