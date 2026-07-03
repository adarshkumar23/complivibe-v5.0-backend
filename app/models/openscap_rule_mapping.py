import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class OpenSCAPRuleMapping(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "openscap_rule_mappings"
    __table_args__ = (
        Index("ix_openscap_rule_mappings_rule_prefix", "rule_prefix"),
        Index("ix_openscap_rule_mappings_control_family", "control_family"),
    )

    rule_prefix: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    control_family: Mapped[str] = mapped_column(String(10), nullable=False)
    control_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
