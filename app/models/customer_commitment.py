import uuid
from datetime import date, datetime

from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
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
        CheckConstraint(
            "obligation_type IS NULL OR obligation_type IN ('breach_notification_sla', 'audit_right', 'data_deletion_timeline', 'subprocessor_restriction', 'data_residency_requirement', 'sla_commitment')",
            name="ck_customer_commitments_obligation_type",
        ),
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="ck_customer_commitments_confidence_score",
        ),
        Index("ix_customer_commitments_org_review", "organization_id", "requires_human_review"),
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

    # -- P9 contract-obligation extraction provenance (migration 0327) --------
    # Set only when a commitment was machine-extracted from a contract clause by
    # the P9 satellite; NULL on every human-created commitment. These are
    # deliberately mapped here rather than left migration-only: without the
    # mapping the columns exist in the database but the ORM silently discards
    # every write to them, which is how the upstream patch shipped.
    obligation_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    extracted_params: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(precision=5, scale=4), nullable=True)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    source_clause_text: Mapped[str | None] = mapped_column(Text, nullable=True)
