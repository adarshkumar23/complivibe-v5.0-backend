import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class PatentScopedKey(UUIDPrimaryKeyMixin, Base):
    """A scoped, service-to-service API key for the P2 satellite integration.

    Deliberately NOT a human RBAC permission -- these keys authenticate the
    external satellite for the patent export/ingest endpoints, one key per
    (organization, key_type). Modeled exactly on CarbonAccountingApiKey: only a
    SHA-256 hash of the key is stored (never the raw key), keys are rotatable in
    place (`rotated_at`), and `is_active` gates them. `key_type` distinguishes
    the two scopes: 'export' -> patent_export:p2:read, 'ingest' ->
    patent_ingest:p2:write.
    """

    __tablename__ = "patent_scoped_keys"
    __table_args__ = (
        CheckConstraint("key_type IN ('export', 'ingest')", name="ck_patent_scoped_keys_key_type"),
        UniqueConstraint("organization_id", "key_type", name="uq_patent_scoped_keys_org_type"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    key_type: Mapped[str] = mapped_column(String(16), nullable=False)
    api_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
