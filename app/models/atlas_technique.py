import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class AtlasTechnique(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "atlas_techniques"
    __table_args__ = (
        CheckConstraint(
            "severity_indicator IS NULL OR severity_indicator IN ('low', 'medium', 'high', 'critical')",
            name="ck_atlas_techniques_severity",
        ),
        Index("ix_atlas_techniques_tactic_code", "tactic_code"),
        Index("ix_atlas_techniques_parent_id", "parent_id"),
        Index("ix_atlas_techniques_atlas_id", "atlas_id"),
    )

    atlas_id: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("atlas_techniques.id", ondelete="SET NULL"),
        nullable=True,
    )
    tactic_code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_subtechnique: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mitigations: Mapped[list] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=list)
    detection_signals: Mapped[list] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=list)
    case_studies: Mapped[list] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=list)
    severity_indicator: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
