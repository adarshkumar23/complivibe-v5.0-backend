import uuid

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class OrganizationObligationState(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "organization_obligation_states"
    __table_args__ = (
        UniqueConstraint("organization_id", "obligation_id", name="uq_org_obligation_state"),
    )

    obligation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("obligations.id", ondelete="CASCADE"), nullable=False)
    applicability_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    implementation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_started")
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
