import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class AmlKycCheck(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "aml_kyc_checks"
    __table_args__ = (
        Index("ix_aml_kyc_checks_org_vendor", "organization_id", "vendor_id"),
        Index("ix_aml_kyc_checks_org_checked", "organization_id", "checked_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    vendor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    signals_used: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    offshore_links_found: Mapped[dict | list] = mapped_column(JSON, nullable=False, default=dict)
    ubo_data: Mapped[dict | list] = mapped_column(JSON, nullable=False, default=dict)
    adverse_media_found: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
