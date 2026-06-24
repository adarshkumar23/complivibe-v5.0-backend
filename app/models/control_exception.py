import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ControlException(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "control_exceptions"
    __table_args__ = (
        CheckConstraint(
            "exception_type IN ('temporary', 'permanent', 'conditional')",
            name="ck_control_exceptions_exception_type",
        ),
        CheckConstraint(
            "status IN ('pending_approval', 'approved', 'rejected', 'active', 'expired', 'revoked', 'cancelled')",
            name="ck_control_exceptions_status",
        ),
        CheckConstraint(
            "expiry_date IS NULL OR expiry_date > effective_date",
            name="ck_control_exceptions_expiry_after_effective",
        ),
        CheckConstraint(
            "(exception_type = 'permanent' AND expiry_date IS NULL) OR (exception_type IN ('temporary', 'conditional') AND expiry_date IS NOT NULL)",
            name="ck_control_exceptions_type_expiry_consistency",
        ),
        Index("ix_control_exceptions_org_control", "organization_id", "control_id"),
        Index("ix_control_exceptions_org_status", "organization_id", "status"),
        Index("ix_control_exceptions_org_expiry", "organization_id", "expiry_date"),
        Index("ix_control_exceptions_org_owner", "organization_id", "owner_user_id"),
    )

    control_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("controls.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    exception_type: Mapped[str] = mapped_column(String(50), nullable=False)
    risk_acceptance_reason: Mapped[str] = mapped_column(Text, nullable=False)

    compensating_control_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("controls.id", ondelete="SET NULL"),
        nullable=True,
    )
    compensating_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending_approval")

    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    rejected_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    revoked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    review_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    auto_expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tags_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
