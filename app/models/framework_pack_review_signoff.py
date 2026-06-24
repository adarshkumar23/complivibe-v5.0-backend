import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class FrameworkPackReviewSignoff(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "framework_pack_review_signoffs"
    __table_args__ = (
        UniqueConstraint("review_run_id", "signer_user_id", name="uq_framework_pack_review_signoff_signer"),
        Index("ix_framework_pack_review_signoffs_org_review", "organization_id", "review_run_id"),
        Index("ix_framework_pack_review_signoffs_org_signed", "organization_id", "signed_at"),
    )

    review_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("framework_pack_review_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    signer_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    signer_role_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    signoff_checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    signoff_signature: Mapped[str | None] = mapped_column(String(128), nullable=True)
    signing_key_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    signature_algorithm: Mapped[str | None] = mapped_column(String(32), nullable=True)
