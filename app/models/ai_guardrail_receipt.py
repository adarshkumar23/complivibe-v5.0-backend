import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AiGuardrailReceipt(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    """Durable store for cryptographically signed decision receipts (patent
    Claim 4).

    Replaces the standalone repo's in-process `receipt_store` dict. Each row is
    one signed receipt in a per-(org, ai_system) hash chain. CompliVibe's core
    stores these receipts but never holds the private signing key -- the key
    lives only in `ReceiptSigner` in the customer's deployment (key-custody
    boundary). `chain_position` gives a total order per chain; the
    `previous_receipt_hash` link is what makes the chain tamper-evident.
    """

    __tablename__ = "ai_guardrail_receipts"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('allow', 'deny')",
            name="ck_ai_guardrail_receipts_decision",
        ),
        UniqueConstraint(
            "organization_id",
            "ai_system_id",
            "chain_position",
            name="uq_ai_guardrail_receipts_org_sys_pos",
        ),
        Index(
            "ix_ai_guardrail_receipts_org_sys_pos",
            "organization_id",
            "ai_system_id",
            "chain_position",
        ),
    )

    ai_system_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_systems.id", ondelete="SET NULL"), nullable=True, index=True
    )
    guardrail_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_derived_guardrails.id", ondelete="SET NULL"), nullable=True
    )
    check_event_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_guardrail_check_events.id", ondelete="SET NULL"), nullable=True
    )
    chain_position: Mapped[int] = mapped_column(Integer, nullable=False)
    receipt_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    receipt_timestamp: Mapped[str] = mapped_column(String(64), nullable=False)
    envelope_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    reasons_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    previous_receipt_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    signature: Mapped[str] = mapped_column(String(256), nullable=False)
    receipt_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    public_key_hex: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
