import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class TrialCode(UUIDPrimaryKeyMixin, Base):
    """A single-use code that grants a 14-day full-feature trial.

    Codes are stored HASHED (SHA-256 hex) -- the plaintext exists only at
    generation time and is written to an out-of-band CSV, never persisted.
    Redemption is single-use, enforced by an atomic `redeemed_at IS NULL`
    claim (see BillingService.redeem_trial_code).
    """

    __tablename__ = "trial_codes"
    __table_args__ = (
        Index("ix_trial_codes_code_hash", "code_hash", unique=True),
        Index("ix_trial_codes_redeemed_at", "redeemed_at"),
    )

    # SHA-256 hex digest of the normalised plaintext code. Unique lookup key.
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # Non-secret leading fragment of the plaintext (e.g. "CV-ABCD"), for support
    # and audit references without exposing a redeemable code.
    code_prefix: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Which generation batch this code belongs to.
    batch_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # NULL = unused. Set atomically on redemption (single-use claim).
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    redeemed_by_org_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
