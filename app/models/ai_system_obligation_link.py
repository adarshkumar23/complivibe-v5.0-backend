import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AiSystemObligationLink(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    """Validated link from an AI system to a derived obligation or control-type
    (patent P2, the "Core Decides" write target).

    Net-new, core-owned: written ONLY by core's ingest path after it has
    independently re-validated a satellite-submitted derivation (never a direct
    satellite write). P2 assumed this table pre-existed; it does not, so it is
    created here.

    Schema note vs. P2's `(obligation_id, control_type_id)` two-nullable-column
    shape: this uses a `link_kind` discriminator + `link_key` so a UNIQUE
    constraint can enforce dedup and enable an atomic `INSERT ... ON CONFLICT DO
    NOTHING` upsert (concurrency-safe), which two nullable columns cannot
    (Postgres treats NULLs as distinct). `link_key` holds the regulatory catalog
    key (e.g. "gdpr_data_subject_rights"), not a core FK.
    """

    __tablename__ = "ai_system_obligation_links"
    __table_args__ = (
        CheckConstraint("link_kind IN ('control_type', 'obligation')", name="ck_ai_system_obligation_links_kind"),
        UniqueConstraint(
            "organization_id", "ai_system_id", "link_kind", "link_key", name="uq_ai_sys_obl_links_org_sys_kind_key"
        ),
        Index("ix_ai_sys_obl_links_org_sys", "organization_id", "ai_system_id"),
    )

    ai_system_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=False
    )
    link_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    link_key: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
