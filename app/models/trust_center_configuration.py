import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class TrustCenterConfiguration(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "trust_center_configurations"
    __table_args__ = (
        CheckConstraint(
            "uptime_status IN ('operational', 'degraded', 'partial_outage', 'major_outage', 'maintenance') OR uptime_status IS NULL",
            name="ck_trust_center_configurations_uptime_status",
        ),
        UniqueConstraint("organization_id", name="uq_trust_center_configurations_organization_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tagline: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    show_certifications: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    show_framework_coverage: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    show_published_policies: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    show_uptime_status: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    uptime_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    uptime_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_access_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    custom_message: Mapped[str | None] = mapped_column(Text, nullable=True)
