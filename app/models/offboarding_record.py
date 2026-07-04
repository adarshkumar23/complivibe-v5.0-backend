import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class OffboardingRecord(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "offboarding_records"
    __table_args__ = (
        Index("ix_offboarding_records_org_deactivated_user", "organization_id", "deactivated_user_id"),
    )

    deactivated_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    successor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    records_reassigned: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    total_reassigned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    executed_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
