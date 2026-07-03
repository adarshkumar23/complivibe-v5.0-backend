import uuid

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class OrganizationExportSetting(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organization_export_settings"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    company_display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    footer_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    primary_color_hex: Mapped[str | None] = mapped_column(String(7), nullable=True)
