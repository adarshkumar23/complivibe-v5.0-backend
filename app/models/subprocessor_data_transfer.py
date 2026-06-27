import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class SubprocessorDataTransfer(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "subprocessor_data_transfers"
    __table_args__ = (
        Index("ix_subprocessor_data_transfers_subprocessor_id", "subprocessor_id"),
        Index("ix_subprocessor_data_transfers_org_destination", "organization_id", "destination_country"),
    )

    subprocessor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("subprocessors.id", ondelete="CASCADE"),
        nullable=False,
    )
    origin_country: Mapped[str] = mapped_column(String(2), nullable=False)
    destination_country: Mapped[str] = mapped_column(String(2), nullable=False)
    data_categories: Mapped[list | dict] = mapped_column(JSON, nullable=False, default=list)
    transfer_mechanism: Mapped[str] = mapped_column(String(100), nullable=False)
    legal_basis: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
