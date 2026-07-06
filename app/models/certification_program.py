import uuid

from sqlalchemy import JSON, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class CertificationProgram(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "certification_programs"
    __table_args__ = (
        Index("ix_certification_programs_name", "name"),
        Index("ix_certification_programs_target_framework", "target_framework"),
        Index("ix_certification_programs_status", "status"),
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    target_framework: Mapped[str] = mapped_column(String(64), nullable=False)
    duration_weeks: Mapped[int] = mapped_column(nullable=False)
    weeks_json: Mapped[list[dict] | None] = mapped_column(JSON, nullable=False, default=list)
    prerequisites_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=False, default=dict)
    evidence_templates_json: Mapped[list[dict] | None] = mapped_column(JSON, nullable=False, default=list)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
