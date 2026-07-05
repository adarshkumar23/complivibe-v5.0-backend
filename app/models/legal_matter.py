import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class LegalMatter(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "legal_matters"
    __table_args__ = (
        CheckConstraint(
            "matter_type IN ('litigation', 'regulatory_inquiry', 'contract_dispute', 'ip_dispute', 'employment', 'other')",
            name="ck_legal_matters_matter_type",
        ),
        CheckConstraint(
            "status IN ('open', 'in_progress', 'on_hold', 'closed')",
            name="ck_legal_matters_status",
        ),
        Index("ix_legal_matters_org_status", "organization_id", "status"),
        Index("ix_legal_matters_org_matter_type", "organization_id", "matter_type"),
        Index("ix_legal_matters_org_related_risk", "organization_id", "related_risk_id"),
        Index("ix_legal_matters_org_related_issue", "organization_id", "related_issue_id"),
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    matter_type: Mapped[str] = mapped_column(String(32), nullable=False, default="other")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    opposing_party: Mapped[str | None] = mapped_column(String(255), nullable=True)
    outside_counsel: Mapped[str | None] = mapped_column(String(255), nullable=True)
    budget: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    related_risk_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("risks.id", ondelete="SET NULL"), nullable=True
    )
    related_issue_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("issues.id", ondelete="SET NULL"), nullable=True
    )
    risk_severity_at_link: Mapped[str | None] = mapped_column(String(16), nullable=True)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
