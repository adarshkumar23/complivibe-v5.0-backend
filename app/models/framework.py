from datetime import date

from sqlalchemy import Date, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Framework(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "frameworks"
    __table_args__ = (UniqueConstraint("code", name="uq_framework_code"),)

    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(128), nullable=False)
    authority: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    coverage_level: Mapped[str] = mapped_column(String(32), nullable=False, default="metadata_only")
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
