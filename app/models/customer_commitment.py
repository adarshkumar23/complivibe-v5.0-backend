import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class CustomerCommitment(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "customer_commitments"
    __table_args__ = (
        CheckConstraint(
            "commitment_type IN ('breach_notification', 'subprocessor_notice', 'audit_right', 'data_deletion', 'data_portability', 'sla', 'security_assessment', 'custom')",
            name="ck_customer_commitments_commitment_type",
        ),
        CheckConstraint(
            "status IN ('active', 'triggered', 'fulfilled', 'overdue', 'waived', 'expired')",
            name="ck_customer_commitments_status",
        ),
        CheckConstraint(
            "notification_days_before >= 1 AND notification_days_before <= 90",
            name="ck_customer_commitments_notification_days_before",
        ),
        Index("ix_customer_commitments_org_status", "organization_id", "status"),
        Index("ix_customer_commitments_org_type", "organization_id", "commitment_type"),
        Index("ix_customer_commitments_trigger_date_status", "trigger_date", "status"),
        Index("ix_customer_commitments_org_owner", "organization_id", "assigned_owner_id"),
        Index("ix_customer_commitments_org_trigger_incident", "organization_id", "triggering_incident_type"),
    )

    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    commitment_type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_condition: Mapped[str] = mapped_column(Text, nullable=False)
    triggering_incident_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    trigger_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notification_days_before: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    sla_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    linked_contract_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    assigned_owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fulfilled_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    fulfillment_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    waived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    waived_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    waiver_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
