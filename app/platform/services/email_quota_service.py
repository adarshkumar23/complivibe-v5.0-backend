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

from sqlalchemy import case, or_, select, update
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

    @staticmethod
    def _window_expired(config: OrgEmailConfig, now: datetime) -> bool:
        """Has the rolling 24h window rolled over? A never-initialised window (NULL
        reset_at) counts as expired -- the org has no live window yet."""
        reset_at = config.sent_today_reset_at
        if reset_at is not None and reset_at.tzinfo is None:
            reset_at = reset_at.replace(tzinfo=UTC)
        return reset_at is None or now >= reset_at

    def check_quota(self, org_id: uuid.UUID) -> tuple[bool, datetime | None]:
        """Return (allowed, retry_at). allowed is False when the org has hit its daily
        cap; retry_at is when the window resets (so the caller can defer).

        This is a pure read. It used to perform the lazy window reset itself, writing
        `sent_today = 0` onto the loaded instance -- a write on a read path, and a
        genuinely destructive one: that pending zero sat in the session and clobbered
        whatever anyone else had counted in the meantime when the session flushed.
        An expired window is now simply *treated* as empty here, and record_sent
        performs the actual reset atomically at the moment it has something to count.
        """
        config = self._config(org_id)
        if config is None:
            return True, None
        if self._window_expired(config, self._now()):
            return True, None
        if config.sent_today >= config.daily_send_limit:
            return False, config.sent_today_reset_at
        return True, None

    def record_sent(self, org_id: uuid.UUID) -> None:
        """Count one successful send against the org's daily window.

        One atomic statement that both rolls the window over and counts the send, so it
        composes with any concurrent writer instead of overwriting them. The previous
        read-modify-write (`config.sent_today += 1`) loses a concurrent increment, and
        losing increments on a send cap means the cap under-counts and the org
        over-sends -- exactly the failure the cap exists to prevent. There is one caller
        today; this makes a second one safe to add rather than a silent regression.

        Whether the window has expired is decided in SQL from the stored reset time,
        not from this session's possibly-stale copy of it.
        """
        config = self._config(org_id)
        if config is None:
            return
        now = self._now()

        # Drop any cached/pending values for the two columns this statement owns, so
        # the session cannot flush a stale copy over the result. Done before execute()
        # because execute() would otherwise autoflush that stale copy first.
        self.db.expire(config, ["sent_today", "sent_today_reset_at"])

        expired = or_(
            OrgEmailConfig.sent_today_reset_at.is_(None),
            OrgEmailConfig.sent_today_reset_at <= now,
        )
        self.db.execute(
            update(OrgEmailConfig)
            .where(OrgEmailConfig.id == config.id)
            .values(
                sent_today=case((expired, 1), else_=OrgEmailConfig.sent_today + 1),
                sent_today_reset_at=case(
                    (expired, now + _WINDOW), else_=OrgEmailConfig.sent_today_reset_at
                ),
            )
            .execution_options(synchronize_session=False)
        )
        self.db.expire(config, ["sent_today", "sent_today_reset_at"])
