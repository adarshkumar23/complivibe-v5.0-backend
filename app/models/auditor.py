from sqlalchemy import Boolean, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Auditor(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "auditors"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    firm: Mapped[str] = mapped_column(String(255), nullable=False)
    certifications_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=False, default=list)
    frameworks_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=False, default=list)
    rate_usd_per_day: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    availability: Mapped[str] = mapped_column(String(64), nullable=False, default="available")
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
