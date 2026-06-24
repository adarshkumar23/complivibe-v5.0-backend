import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AISystemGovernanceAttestation(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_system_governance_attestations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "review_id",
            "signer_user_id",
            name="uq_ai_system_gov_attestation_signer_per_review",
        ),
        Index("ix_ai_system_gov_attestations_org_ai_system", "organization_id", "ai_system_id"),
        Index("ix_ai_system_gov_attestations_org_review", "organization_id", "review_id"),
        Index("ix_ai_system_gov_attestations_org_signed_at", "organization_id", "signed_at"),
    )

    ai_system_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_systems.id", ondelete="CASCADE"),
        nullable=False,
    )
    review_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_system_governance_reviews.id", ondelete="CASCADE"),
        nullable=False,
    )
    signer_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    signer_role_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    checklist_snapshot_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    review_snapshot_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    signature_algorithm: Mapped[str] = mapped_column(String(32), nullable=False)
    internal_signature: Mapped[str] = mapped_column(String(128), nullable=False)
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    caveat: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
