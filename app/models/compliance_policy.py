import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class CompliancePolicy(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "compliance_policies"
    __table_args__ = (
        Index("ix_compliance_policies_org_status", "organization_id", "status"),
        Index("ix_compliance_policies_org_type", "organization_id", "policy_type"),
        Index("ix_compliance_policies_org_owner", "organization_id", "owner_user_id"),
        Index("ix_compliance_policies_org_archived", "organization_id", "archived_at"),
        Index("ix_compliance_policies_org_review_due", "organization_id", "review_due_date"),
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")

    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    review_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0")
    content_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    tags_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    archive_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("business_units.id", ondelete="SET NULL"),
        nullable=True,
    )
    ai_drafted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_import_tool: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_ai_draft_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "ai_content_drafts.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_compliance_policies_source_ai_draft_id",
        ),
        nullable=True,
    )
