from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # A non-human automation principal. Exists because several core tables require a
    # real users.id FK for authorship (issues.created_by/owner_id, ai_governance_reviews
    # .created_by are all NOT NULL RESTRICT) and there is no nullable path.
    #
    # It must stay is_active=True and status='active' so membership checks pass, which
    # is precisely why it needs its own flag: no existing column can distinguish it from
    # a person. Every people-facing surface (member lists, owner/assignee pickers, seat
    # counts, notification fan-out, SCIM) must exclude it by default. See
    # app/services/system_account_service.py for the pattern and the full surface list.
    is_system_account: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
