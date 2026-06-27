import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AuditorPortalInvitation(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "auditor_portal_invitations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'revoked', 'expired')",
            name="ck_auditor_portal_invitations_status",
        ),
        Index("ix_auditor_portal_invitations_token_hash", "token_hash"),
        Index("ix_auditor_portal_invitations_org_engagement", "organization_id", "audit_engagement_id"),
        Index("ix_auditor_portal_invitations_org_status", "organization_id", "status"),
    )

    audit_engagement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("audit_engagements.id", ondelete="CASCADE"),
        nullable=False,
    )
    auditor_email: Mapped[str] = mapped_column(String(255), nullable=False)
    auditor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    scoped_framework_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    scoped_control_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    scoped_evidence_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    access_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
