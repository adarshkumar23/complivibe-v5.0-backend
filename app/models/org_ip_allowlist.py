from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class OrgIPAllowlist(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "org_ip_allowlist"
    __table_args__ = (
        Index("ix_org_ip_allowlist_org_active", "organization_id", "is_active"),
    )

    cidr_range: Mapped[str] = mapped_column(String(50), nullable=False)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
