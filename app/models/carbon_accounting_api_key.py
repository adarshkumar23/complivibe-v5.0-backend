import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CarbonAccountingApiKey(Base):
    """Dedicated, org-scoped ingest API key for POST /carbon-accounting/readings.

    Deliberately separate from the OpenMetadata lineage integration's ingest key --
    the two features are unrelated, and coupling carbon-accounting auth to lineage
    config meant carbon ingestion was 100% dead for any org that hadn't also set up
    an OpenMetadata integration (see G9 item 12).
    """

    __tablename__ = "carbon_accounting_api_keys"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_carbon_accounting_api_keys_org"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    api_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
