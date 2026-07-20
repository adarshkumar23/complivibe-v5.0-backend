from __future__ import annotations

from datetime import UTC, datetime, timedelta

try:
    import sentry_sdk
except Exception:  # pragma: no cover - optional in local test environments
    sentry_sdk = None  # type: ignore[assignment]

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.email_outbox import EmailOutbox
from app.platform.services.email_quota_service import EmailQuotaService
from app.platform.services.ses_service import SESService
from app.services.email_service import EmailService


class EmailOutboxFlushService:
    def __init__(self, db: Session):
        self.db = db
        self.ses = SESService()
        self.email_service = EmailService(db)
        self.quota = EmailQuotaService(db)

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _capture_terminal_failure(email: EmailOutbox) -> None:
        settings = get_settings()
        if not settings.SENTRY_DSN or sentry_sdk is None:
            return

        error_text = (
            getattr(email, "last_error", None)
            or f"Email delivery exhausted retries for {email.recipient_email}"
        )
        sentry_sdk.capture_exception(RuntimeError(str(error_text)))

    def flush(self, batch_size: int = 50) -> dict:
        now = self.utcnow()
        rows = self.db.execute(
            select(EmailOutbox)
            .where(
                EmailOutbox.status.in_(["pending", "failed"]),
                or_(EmailOutbox.scheduled_at.is_(None), EmailOutbox.scheduled_at <= now),
                or_(EmailOutbox.next_attempt_at.is_(None), EmailOutbox.next_attempt_at <= now),
                or_(EmailOutbox.lock_expires_at.is_(None), EmailOutbox.lock_expires_at <= now),
            )
            .order_by(EmailOutbox.created_at.asc())
            .limit(max(1, min(batch_size, 50)))
        ).scalars().all()

        sent = 0
        failed = 0
        skipped = 0

        for email in rows:
            if self.email_service.enforce_outbox_notification_preference(
                email,
                actor_user_id=email.created_by_user_id,
            ):
                skipped += 1
                continue

            retry_count = int(getattr(email, "retry_count", 0) or 0)
            attempt_count = int(getattr(email, "attempt_count", 0) or 0)
            max_attempts = int(getattr(email, "max_attempts", 3) or 3)
            hard_limit = min(max_attempts, 3)

            if retry_count >= hard_limit or attempt_count >= hard_limit:
                email.status = "failed"
                email.failed_at = now
                self._capture_terminal_failure(email)
                skipped += 1
                continue

            # Per-org daily send cap (OrgEmailConfig.daily_send_limit). Over the cap we
            # defer this row to the next window instead of sending, so an authenticated
            # insider (or a compromised org account) cannot burn unlimited SES quota /
            # sender reputation. Leaves the row pending; it drains after the reset.
            allowed, retry_at = self.quota.check_quota(email.organization_id)
            if not allowed:
                email.status = "pending"
                email.next_attempt_at = retry_at or (now + timedelta(hours=1))
                email.locked_at = None
                email.lock_expires_at = None
                email.locked_by = None
                skipped += 1
                continue

            result = self.ses.send_email(
                to_email=email.recipient_email,
                subject=email.subject,
                html_body=email.body_html or email.body_text,
                text_body=email.body_text,
                org_id=email.organization_id,
                db=self.db,
            )

            email.last_attempt_at = now
            email.attempt_count = attempt_count + 1
            email.retry_count = retry_count + (0 if result["success"] else 1)
            email.provider = "ses"
            email.locked_at = None
            email.lock_expires_at = None
            email.locked_by = None

            if result["success"]:
                self.quota.record_sent(email.organization_id)
                email.status = "sent"
                email.sent_at = now
                email.failed_at = None
                email.last_error = None
                email.next_attempt_at = None
                message_id = result.get("message_id")
                if message_id:
                    email.provider_message_id = message_id
                    email.ses_message_id = message_id
                sent += 1
            else:
                email.last_error = result.get("error")
                email.failed_at = now
                if email.retry_count >= hard_limit:
                    email.status = "failed"
                    email.next_attempt_at = None
                    self._capture_terminal_failure(email)
                else:
                    email.status = "pending"
                    email.next_attempt_at = now + timedelta(minutes=5)
                failed += 1

        self.db.flush()
        return {
            "sent": sent,
            "failed": failed,
            "skipped": skipped,
            "total_processed": len(rows),
        }
