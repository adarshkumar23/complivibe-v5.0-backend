from datetime import datetime

from sqlalchemy import DateTime, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SanctionsEntity(Base):
    __tablename__ = "sanctions_entities"
    __table_args__ = (
        Index("ix_sanctions_entities_caption", "caption"),
        Index("ix_sanctions_entities_schema", "schema_type"),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    caption: Mapped[str] = mapped_column(String(1024), nullable=False)
    schema_type: Mapped[str] = mapped_column(String(100), nullable=False)
    countries: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    datasets: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    properties: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
