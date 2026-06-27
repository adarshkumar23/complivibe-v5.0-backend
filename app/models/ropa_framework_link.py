import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class RopaFrameworkLink(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ropa_framework_links"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "processing_activity_id",
            "obligation_id",
            name="uq_ropa_framework_links_org_activity_obligation",
        ),
        Index("ix_ropa_framework_links_org_activity", "organization_id", "processing_activity_id"),
        Index("ix_ropa_framework_links_org_obligation", "organization_id", "obligation_id"),
    )

    processing_activity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("processing_activities.id", ondelete="CASCADE"),
        nullable=False,
    )
    obligation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("obligations.id", ondelete="CASCADE"), nullable=False)
    linked_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
