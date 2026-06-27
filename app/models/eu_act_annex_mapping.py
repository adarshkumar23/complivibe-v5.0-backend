from sqlalchemy import Boolean, CheckConstraint, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class EUActAnnexMapping(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "eu_act_annex_mappings"
    __table_args__ = (
        CheckConstraint("annex_type IN ('annex_i', 'annex_iii')", name="ck_eu_act_annex_mappings_type"),
        UniqueConstraint("annex_ref", name="uq_eu_act_annex_ref"),
        Index("ix_eu_act_annex_mappings_ref", "annex_ref"),
    )

    annex_ref: Mapped[str] = mapped_column(String(20), nullable=False)
    annex_type: Mapped[str] = mapped_column(String(20), nullable=False)
    sector: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    article_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
