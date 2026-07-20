import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin

# The inbound machine-ingest subsystems that each get their OWN key. Previously they
# all authenticated against the single OpenMetadata/data-lineage integration key, so
# a key leaked from any one (e.g. a PAM agent) authenticated all the others for that
# org. One key per (organization, key_type) isolates them.
SUBSYSTEM_KEY_TYPES: tuple[str, ...] = (
    "lineage",
    "cookies",
    "consent",
    "security",
    "access_monitoring",
    "pam",
)


class SubsystemIngestKey(UUIDPrimaryKeyMixin, Base):
    """Per-(organization, subsystem) inbound machine-ingest API key.

    Modeled exactly on PatentScopedKey / CarbonAccountingApiKey: only a SHA-256 hash
    of the key is stored (never the raw key), one active key per (org, key_type),
    rotatable in place (`rotated_at`), gated by `is_active`. Resolution is a direct
    indexed lookup on `api_key_hash` (see ix_subsystem_ingest_keys_api_key_hash),
    replacing the previous O(active-orgs) decrypt-and-compare loop and keying trust
    to a single subsystem via `key_type`.
    """

    __tablename__ = "subsystem_ingest_keys"
    __table_args__ = (
        CheckConstraint(
            "key_type IN ('lineage', 'cookies', 'consent', 'security', 'access_monitoring', 'pam')",
            name="ck_subsystem_ingest_keys_key_type",
        ),
        UniqueConstraint("organization_id", "key_type", name="uq_subsystem_ingest_keys_org_type"),
        Index("ix_subsystem_ingest_keys_api_key_hash", "api_key_hash"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    key_type: Mapped[str] = mapped_column(String(32), nullable=False)
    api_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
