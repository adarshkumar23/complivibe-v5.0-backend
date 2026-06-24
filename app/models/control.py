import uuid

from sqlalchemy import ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Control(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "controls"
    __table_args__ = (
        Index("ix_control_org_status", "organization_id", "status"),
        Index("ix_controls_owner_user_id", "owner_id"),
    )

    obligation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("obligations.id", ondelete="SET NULL"), nullable=True
    )
    control_code: Mapped[str | None] = mapped_column("code", String(120), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    control_type: Mapped[str] = mapped_column(String(32), nullable=False, default="process")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_started")
    criticality: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        "owner_id", Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    testing_procedure: Mapped[str | None] = mapped_column(Text, nullable=True)
    implementation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="custom")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    suggestion_source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("obligation_control_suggestions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
