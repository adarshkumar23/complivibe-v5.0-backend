import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class EUActFRIA(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "eu_act_frias"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'in_progress', 'complete')",
            name="ck_eu_act_frias_status",
        ),
        Index("ix_eu_act_frias_org_system", "organization_id", "ai_system_id"),
        Index("ix_eu_act_frias_org_status", "organization_id", "status"),
    )

    ai_system_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=False)
    rights_affected: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    risk_to_rights_assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    mitigation_measures: Mapped[str | None] = mapped_column(Text, nullable=True)
    consultation_conducted: Mapped[bool] = mapped_column(nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
