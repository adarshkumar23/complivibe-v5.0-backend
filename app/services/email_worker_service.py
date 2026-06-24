import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.email_outbox import EmailOutbox
from app.services.email_service import EmailService


class EmailWorkerService:
    LOCK_TTL_SECONDS = 300

    def __init__(self, db: Session) -> None:
        self.db = db
        self.email_service = EmailService(db)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    def calculate_next_attempt_at(self, attempt_count: int) -> datetime:
        now = self._now()
        if attempt_count <= 1:
            return now + timedelta(minutes=5)
        if attempt_count == 2:
            return now + timedelta(minutes=15)
        if attempt_count == 3:
            return now + timedelta(hours=1)
        return now + timedelta(hours=6)

    def claim_pending_emails(
        self,
        *,
        organization_id: uuid.UUID,
        worker_id: str,
        limit: int,
        actor_user_id: uuid.UUID | None,
    ) -> list[EmailOutbox]:
        now = self._now()
        stmt = (
            select(EmailOutbox)
            .where(
                EmailOutbox.organization_id == organization_id,
                EmailOutbox.status.in_(["pending", "failed"]),
                or_(EmailOutbox.scheduled_at.is_(None), EmailOutbox.scheduled_at <= now),
                or_(EmailOutbox.next_attempt_at.is_(None), EmailOutbox.next_attempt_at <= now),
            )
            .order_by(EmailOutbox.queued_at.asc())
            .limit(limit)
            .with_for_update()
        )
        candidates = self.db.execute(stmt).scalars().all()

        claimed: list[EmailOutbox] = []
        for item in candidates:
            if item.status == "processing" and item.lock_expires_at and item.lock_expires_at > now:
                continue
            if item.status in {"cancelled", "sent", "skipped", "dead_letter"}:
                continue

            previous_status = item.status
            item.status = "processing"
            item.locked_at = now
            item.locked_by = worker_id
            item.lock_expires_at = now + timedelta(seconds=self.LOCK_TTL_SECONDS)
            item.worker_metadata_json = {"worker_id": worker_id, "claimed_at": now.isoformat()}
            self.email_service.add_delivery_event(
                organization_id=organization_id,
                email_outbox_id=item.id,
                event_type="email.claimed",
                status_from=previous_status,
                status_to=item.status,
                details_json={"worker_id": worker_id},
                created_by_user_id=actor_user_id,
            )
            claimed.append(item)

        self.db.flush()
        return claimed

    def _require_processing_lock(self, *, email: EmailOutbox, worker_id: str) -> None:
        if email.status != "processing":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email must be in processing status")
        if email.locked_by != worker_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email is locked by another worker")

    def complete_email(
        self,
        *,
        email: EmailOutbox,
        worker_id: str,
        actor_user_id: uuid.UUID | None,
        provider_message_id: str | None = None,
    ) -> EmailOutbox:
        self._require_processing_lock(email=email, worker_id=worker_id)

        previous_status = email.status
        now = self._now()
        email.status = "sent"
        email.sent_at = now
        email.last_attempt_at = now
        email.provider_message_id = provider_message_id
        email.locked_at = None
        email.locked_by = None
        email.lock_expires_at = None

        self.email_service.add_delivery_event(
            organization_id=email.organization_id,
            email_outbox_id=email.id,
            event_type="email.worker_completed",
            status_from=previous_status,
            status_to=email.status,
            details_json={"worker_id": worker_id},
            created_by_user_id=actor_user_id,
        )
        self.db.flush()
        return email

    def move_to_dead_letter(
        self,
        *,
        email: EmailOutbox,
        reason: str,
        actor_user_id: uuid.UUID | None,
        worker_id: str | None = None,
        event_type: str = "email.dead_lettered",
    ) -> EmailOutbox:
        if email.status in {"sent", "cancelled"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email cannot be dead-lettered from current status")

        previous_status = email.status
        now = self._now()
        email.status = "dead_letter"
        email.dead_lettered_at = now
        email.failed_at = now
        email.last_error = reason
        email.locked_at = None
        email.locked_by = None
        email.lock_expires_at = None
        email.next_attempt_at = None

        details: dict[str, str] = {"reason": reason}
        if worker_id:
            details["worker_id"] = worker_id

        self.email_service.add_delivery_event(
            organization_id=email.organization_id,
            email_outbox_id=email.id,
            event_type=event_type,
            status_from=previous_status,
            status_to=email.status,
            details_json=details,
            created_by_user_id=actor_user_id,
        )
        self.db.flush()
        return email

    def fail_email(
        self,
        *,
        email: EmailOutbox,
        worker_id: str,
        error_message: str,
        actor_user_id: uuid.UUID | None,
        retry_after_seconds: int | None = None,
    ) -> EmailOutbox:
        self._require_processing_lock(email=email, worker_id=worker_id)

        now = self._now()
        previous_status = email.status
        email.attempt_count += 1
        email.failed_at = now
        email.last_attempt_at = now
        email.last_error = error_message

        if email.attempt_count >= email.max_attempts:
            return self.move_to_dead_letter(
                email=email,
                reason=error_message,
                actor_user_id=actor_user_id,
                worker_id=worker_id,
                event_type="email.dead_lettered",
            )

        email.status = "failed"
        email.next_attempt_at = (
            now + timedelta(seconds=retry_after_seconds)
            if retry_after_seconds is not None and retry_after_seconds > 0
            else self.calculate_next_attempt_at(email.attempt_count)
        )
        email.locked_at = None
        email.locked_by = None
        email.lock_expires_at = None

        self.email_service.add_delivery_event(
            organization_id=email.organization_id,
            email_outbox_id=email.id,
            event_type="email.worker_failed",
            status_from=previous_status,
            status_to=email.status,
            details_json={
                "worker_id": worker_id,
                "error": error_message,
                "attempt_count": email.attempt_count,
                "next_attempt_at": email.next_attempt_at.isoformat() if email.next_attempt_at else None,
            },
            created_by_user_id=actor_user_id,
        )
        self.db.flush()
        return email

    def release_expired_locks(
        self,
        *,
        organization_id: uuid.UUID | None,
        actor_user_id: uuid.UUID | None,
    ) -> list[EmailOutbox]:
        now = self._now()
        filters = [
            EmailOutbox.status == "processing",
            EmailOutbox.lock_expires_at.is_not(None),
            EmailOutbox.lock_expires_at < now,
        ]
        if organization_id is not None:
            filters.append(EmailOutbox.organization_id == organization_id)

        stmt = select(EmailOutbox).where(and_(*filters)).with_for_update()
        rows = self.db.execute(stmt).scalars().all()

        released: list[EmailOutbox] = []
        for item in rows:
            previous_status = item.status
            if item.attempt_count >= item.max_attempts:
                self.move_to_dead_letter(
                    email=item,
                    reason="Lock expired and max attempts reached",
                    actor_user_id=actor_user_id,
                    event_type="email.dead_lettered",
                )
            else:
                item.status = "failed"
                item.next_attempt_at = now
                item.last_error = "Lock expired before processing completed"
                item.locked_at = None
                item.locked_by = None
                item.lock_expires_at = None
                self.email_service.add_delivery_event(
                    organization_id=item.organization_id,
                    email_outbox_id=item.id,
                    event_type="email.expired_lock_released",
                    status_from=previous_status,
                    status_to=item.status,
                    details_json=None,
                    created_by_user_id=actor_user_id,
                )
            released.append(item)

        self.db.flush()
        return released
