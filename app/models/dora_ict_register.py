import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class DORAICTRegister(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "dora_ict_register"
    __table_args__ = (
        CheckConstraint(
            "assessment_frequency IN ('annual', 'biannual', 'quarterly', 'continuous') OR assessment_frequency IS NULL",
            name="ck_dora_ict_register_assessment_frequency",
        ),
        CheckConstraint(
            "status IN ('active', 'under_review', 'terminated')",
            name="ck_dora_ict_register_status",
        ),
        Index("ix_dora_ict_register_org_critical", "organization_id", "is_critical_function"),
        Index("ix_dora_ict_register_org_status", "organization_id", "status"),
        Index("ix_dora_ict_register_org_vendor", "organization_id", "vendor_id"),
    )

    vendor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    counterparty_name: Mapped[str] = mapped_column(String(255), nullable=False)
    service_description: Mapped[str] = mapped_column(Text, nullable=False)
    is_critical_function: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sub_outsourcing_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    data_location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    data_location_countries: Mapped[list | dict] = mapped_column(JSON, nullable=False, default=list)
    contract_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    exit_strategy_documented: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    exit_strategy_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assessment_frequency: Mapped[str | None] = mapped_column(String(20), nullable=True)
    dora_article: Mapped[str] = mapped_column(String(20), nullable=False, default="Art.28")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
