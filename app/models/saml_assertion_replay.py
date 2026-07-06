import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class SAMLAssertionReplay(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "saml_assertion_replays"
    __table_args__ = (
        Index("ix_saml_assertion_replays_org_assertion", "organization_id", "assertion_id", unique=True),
        Index("ix_saml_assertion_replays_org_expires", "organization_id", "expires_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sso_config_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("sso_configs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assertion_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name_id: Mapped[str | None] = mapped_column(String(320), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
