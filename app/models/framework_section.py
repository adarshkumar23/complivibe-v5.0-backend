import uuid

from sqlalchemy import ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class FrameworkSection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "framework_sections"
    __table_args__ = (
        Index("ix_framework_sections_framework", "framework_id"),
        Index("ix_framework_sections_framework_version", "framework_version_id"),
        Index("ix_framework_sections_parent", "parent_section_id"),
        Index("ix_framework_sections_code", "framework_id", "section_code"),
    )

    framework_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("frameworks.id", ondelete="CASCADE"), nullable=False)
    framework_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("framework_versions.id", ondelete="SET NULL"), nullable=True)
    parent_section_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("framework_sections.id", ondelete="SET NULL"), nullable=True)
    section_code: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
