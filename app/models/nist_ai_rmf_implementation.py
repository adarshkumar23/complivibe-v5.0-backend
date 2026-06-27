import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class NISTAIRMFImplementation(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "nist_ai_rmf_implementations"
    __table_args__ = (
        CheckConstraint(
            "govern_status IN ('not_started', 'in_progress', 'implemented')",
            name="ck_nist_ai_rmf_implementations_govern_status",
        ),
        CheckConstraint(
            "map_status IN ('not_started', 'in_progress', 'implemented')",
            name="ck_nist_ai_rmf_implementations_map_status",
        ),
        CheckConstraint(
            "measure_status IN ('not_started', 'in_progress', 'implemented')",
            name="ck_nist_ai_rmf_implementations_measure_status",
        ),
        CheckConstraint(
            "manage_status IN ('not_started', 'in_progress', 'implemented')",
            name="ck_nist_ai_rmf_implementations_manage_status",
        ),
        UniqueConstraint("organization_id", "ai_system_id", name="uq_nist_ai_rmf_implementations_org_system"),
        Index("ix_nist_ai_rmf_implementations_org_system", "organization_id", "ai_system_id"),
    )

    ai_system_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=False)
    govern_status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_started")
    map_status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_started")
    measure_status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_started")
    manage_status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_started")
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
