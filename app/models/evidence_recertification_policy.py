import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class EvidenceRecertificationPolicy(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "evidence_recertification_policies"
    __table_args__ = (
        Index("ix_recert_policy_org_status", "organization_id", "status"),
        Index("ix_recert_policy_org_next_run", "organization_id", "next_run_at"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cadence: Mapped[str] = mapped_column(String(32), nullable=False)
    lead_time_days: Mapped[int] = mapped_column(nullable=False, default=14)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
