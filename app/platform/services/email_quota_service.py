"""Per-org daily email send-cap enforcement.

OrgEmailConfig.daily_send_limit / sent_today have existed as columns since the email
config was added, but nothing read or incremented them -- the cap was dead. This service
makes them live: the outbox drain checks the quota before each send and records a send on
success, with a lazily-reset rolling 24h window.

Orgs with no OrgEmailConfig row have no configured cap and are not throttled here (they
remain bounded by the email rate-limit group and the SES account quota).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.org_email_config import OrgEmailConfig

_WINDOW = timedelta(hours=24)


class EmailQuotaService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    def _config(self, org_id: uuid.UUID) -> OrgEmailConfig | None:
        return self.db.execute(
            select(OrgEmailConfig).where(OrgEmailConfig.organization_id == org_id)
        ).scalar_one_or_none()

    def _maybe_reset(self, config: OrgEmailConfig, now: datetime) -> None:
        reset_at = config.sent_today_reset_at
        if reset_at is not None and reset_at.tzinfo is None:
            reset_at = reset_at.replace(tzinfo=UTC)
        if reset_at is None or now >= reset_at:
            config.sent_today = 0
            config.sent_today_reset_at = now + _WINDOW

    def check_quota(self, org_id: uuid.UUID) -> tuple[bool, datetime | None]:
        """Return (allowed, retry_at). allowed is False when the org has hit its daily
        cap; retry_at is when the window resets (so the caller can defer)."""
        config = self._config(org_id)
        if config is None:
            return True, None
        self._maybe_reset(config, self._now())
        if config.sent_today >= config.daily_send_limit:
            return False, config.sent_today_reset_at
        return True, None

    def record_sent(self, org_id: uuid.UUID) -> None:
        """Count one successful send against the org's daily window."""
        config = self._config(org_id)
        if config is None:
            return
        self._maybe_reset(config, self._now())
        config.sent_today += 1
