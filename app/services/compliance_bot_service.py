import hashlib
import hmac
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.compliance.services.digest_service import DigestService
from app.compliance.services.employee_attestation_service import AttestationRecordService
from app.compliance.services.sla_service import SLAService
from app.models.compliance_bot_outbox import ComplianceBotOutbox
from app.models.compliance_bot_subscription import ComplianceBotSubscription
from app.models.evidence_item import EvidenceItem
from app.models.policy_attestation_record import PolicyAttestationRecord
from app.models.risk import Risk
from app.models.task import Task
from app.models.user import User
from app.services.audit_service import AuditService
from app.services.rbac_service import RBACService

logger = logging.getLogger(__name__)

# A subscription that hasn't had any successful digest/SLA-alert dispatch in
# this long, despite being active and enabled, is flagged as needing a look.
SUBSCRIPTION_STALE_THRESHOLD_DAYS = 14


class ComplianceBotService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _normalize_time(value: str) -> str:
        try:
            hh, mm = value.split(":")
            hour = int(hh)
            minute = int(mm)
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
            return f"{hour:02d}:{minute:02d}"
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid digest_time_utc format") from exc

    def upsert_subscription(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        platform: str,
        channel_ref: str,
        is_active: bool,
        digest_enabled: bool,
        digest_time_utc: str,
        sla_alerts_enabled: bool,
        actor_user_id: uuid.UUID,
        platform_user_ref: str | None = None,
    ) -> ComplianceBotSubscription:
        row = (
            self.db.execute(
                select(ComplianceBotSubscription).where(
                    ComplianceBotSubscription.organization_id == organization_id,
                    ComplianceBotSubscription.user_id == user_id,
                    ComplianceBotSubscription.platform == platform,
                )
            )
            .scalars()
            .one_or_none()
        )
        normalized_time = self._normalize_time(digest_time_utc)
        if row is None:
            row = ComplianceBotSubscription(
                organization_id=organization_id,
                user_id=user_id,
                platform=platform,
                channel_ref=channel_ref,
                is_active=is_active,
                digest_enabled=digest_enabled,
                digest_time_utc=normalized_time,
                sla_alerts_enabled=sla_alerts_enabled,
                created_by_user_id=actor_user_id,
                platform_user_ref=platform_user_ref,
            )
            self.db.add(row)
            self.db.flush()
            AuditService(self.db).write_audit_log(
                action="compliance_bot.subscription_created",
                entity_type="compliance_bot_subscription",
                entity_id=row.id,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                after_json={
                    "platform": row.platform,
                    "channel_ref": row.channel_ref,
                    "digest_time_utc": row.digest_time_utc,
                },
                metadata_json={"source": "api"},
            )
            return row

        before = {
            "channel_ref": row.channel_ref,
            "is_active": row.is_active,
            "digest_enabled": row.digest_enabled,
            "digest_time_utc": row.digest_time_utc,
            "sla_alerts_enabled": row.sla_alerts_enabled,
        }
        row.channel_ref = channel_ref
        row.is_active = is_active
        row.digest_enabled = digest_enabled
        row.digest_time_utc = normalized_time
        row.sla_alerts_enabled = sla_alerts_enabled
        if platform_user_ref is not None:
            row.platform_user_ref = platform_user_ref
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="compliance_bot.subscription_updated",
            entity_type="compliance_bot_subscription",
            entity_id=row.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json={
                "channel_ref": row.channel_ref,
                "is_active": row.is_active,
                "digest_enabled": row.digest_enabled,
                "digest_time_utc": row.digest_time_utc,
                "sla_alerts_enabled": row.sla_alerts_enabled,
            },
            metadata_json={"source": "api"},
        )
        return row

    @staticmethod
    def _as_aware(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    def describe_subscription_context(self, subscription: ComplianceBotSubscription) -> list[str]:
        """Flag subscriptions that are configured to receive proactive messages but have
        never (or not recently) actually had one dispatched, so an admin can tell a
        channel/webhook has gone dark instead of silently assuming delivery is healthy."""
        flags: list[str] = []
        if not subscription.is_active:
            return flags
        now = self.utcnow()
        created_at = self._as_aware(subscription.created_at)
        old_enough = created_at is not None and (now - created_at) > timedelta(days=SUBSCRIPTION_STALE_THRESHOLD_DAYS)

        if subscription.digest_enabled:
            last_digest = self._as_aware(subscription.last_digest_sent_at)
            if last_digest is None and old_enough:
                flags.append("digest_pending_first_send")
            elif last_digest is not None and (now - last_digest) > timedelta(days=SUBSCRIPTION_STALE_THRESHOLD_DAYS):
                flags.append("digest_stale")

        if subscription.sla_alerts_enabled:
            last_sla = self._as_aware(subscription.last_sla_alert_sent_at)
            if last_sla is None and old_enough:
                flags.append("sla_alerts_pending_first_check")

        return flags

    def list_subscriptions(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> list[ComplianceBotSubscription]:
        return (
            self.db.execute(
                select(ComplianceBotSubscription)
                .where(
                    ComplianceBotSubscription.organization_id == organization_id,
                    ComplianceBotSubscription.user_id == user_id,
                )
                .order_by(ComplianceBotSubscription.platform.asc())
            )
            .scalars()
            .all()
        )

    def _subscription_or_404(self, organization_id: uuid.UUID, user_id: uuid.UUID, platform: str) -> ComplianceBotSubscription:
        row = (
            self.db.execute(
                select(ComplianceBotSubscription).where(
                    ComplianceBotSubscription.organization_id == organization_id,
                    ComplianceBotSubscription.user_id == user_id,
                    ComplianceBotSubscription.platform == platform,
                    ComplianceBotSubscription.is_active.is_(True),
                )
            )
            .scalars()
            .one_or_none()
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compliance bot subscription not found")
        return row

    @staticmethod
    def verify_webhook_signature(webhook_secret: str | None, *, raw_body: bytes, signature: str | None) -> None:
        """Verify the HMAC-SHA256 signature on an inbound compliance-bot Slack/Teams
        webhook request, the same signature-only pattern the Razorpay webhook and
        the Jira/Linear issue-sync webhooks use in place of a Bearer JWT (which real
        Slack/Teams webhook traffic can never present).
        """
        if not webhook_secret:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Organization has no compliance_bot_webhook_secret configured",
            )
        if not signature:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing webhook signature")
        expected = hmac.new(webhook_secret.encode(), raw_body, hashlib.sha256).hexdigest()
        provided = signature.strip().lower()
        if provided.startswith("sha256="):
            provided = provided[len("sha256="):]
        if not hmac.compare_digest(expected, provided):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")

    def resolve_actor_by_platform_ref(self, organization_id: uuid.UUID, platform: str, platform_user_ref: str) -> uuid.UUID:
        """Resolve which CompliVibe user issued a signature-authenticated webhook
        command, from the external Slack/Teams user id -- used instead of a Bearer
        JWT, which real Slack/Teams webhook traffic never carries."""
        user_id = self.db.execute(
            select(ComplianceBotSubscription.user_id).where(
                ComplianceBotSubscription.organization_id == organization_id,
                ComplianceBotSubscription.platform == platform,
                ComplianceBotSubscription.platform_user_ref == platform_user_ref,
                ComplianceBotSubscription.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No compliance bot subscription is linked to this Slack/Teams user for this organization",
            )
        return user_id

    def _queue_outbox(
        self,
        *,
        organization_id: uuid.UUID,
        subscription: ComplianceBotSubscription,
        message_type: str,
        content_text: str,
        payload_json: dict,
        command_text: str | None,
        status_value: str,
        scheduled_for: datetime,
        sent_at: datetime | None = None,
        error_message: str | None = None,
        idempotency_key: str | None = None,
    ) -> ComplianceBotOutbox:
        row = ComplianceBotOutbox(
            organization_id=organization_id,
            subscription_id=subscription.id,
            message_type=message_type,
            status=status_value,
            command_text=command_text,
            content_text=content_text,
            payload_json=payload_json,
            scheduled_for=scheduled_for,
            sent_at=sent_at,
            error_message=error_message,
            idempotency_key=idempotency_key,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _status_payload(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> dict:
        overdue_tasks = int(
            self.db.execute(
                select(func.count(Task.id)).where(
                    Task.organization_id == organization_id,
                    Task.owner_user_id == user_id,
                    Task.status.in_(["open", "in_progress", "blocked"]),
                    Task.due_date.is_not(None),
                    Task.due_date < self.utcnow(),
                )
            ).scalar_one()
            or 0
        )
        pending_attestations = int(
            self.db.execute(
                select(func.count(PolicyAttestationRecord.id)).where(
                    PolicyAttestationRecord.organization_id == organization_id,
                    PolicyAttestationRecord.user_id == user_id,
                    PolicyAttestationRecord.status == "pending",
                )
            ).scalar_one()
            or 0
        )
        high_risks = int(
            self.db.execute(
                select(func.count(Risk.id)).where(
                    Risk.organization_id == organization_id,
                    Risk.owner_user_id == user_id,
                    Risk.status.notin_(["closed", "accepted"]),
                    Risk.severity.in_(["high", "critical"]),
                )
            ).scalar_one()
            or 0
        )
        evidence_needs_review = int(
            self.db.execute(
                select(func.count(EvidenceItem.id)).where(
                    EvidenceItem.organization_id == organization_id,
                    EvidenceItem.review_status.in_(["not_reviewed", "needs_review"]),
                    EvidenceItem.status == "active",
                )
            ).scalar_one()
            or 0
        )
        return {
            "overdue_tasks": overdue_tasks,
            "pending_attestations": pending_attestations,
            "high_risks": high_risks,
            "evidence_needs_review": evidence_needs_review,
        }

    def _top_tasks_payload(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> list[dict]:
        rows = (
            self.db.execute(
                select(Task).where(
                    Task.organization_id == organization_id,
                    Task.owner_user_id == user_id,
                    Task.status.in_(["open", "in_progress", "blocked"]),
                )
                .order_by(Task.due_date.asc().nullslast(), Task.created_at.desc())
                .limit(5)
            )
            .scalars()
            .all()
        )
        return [
            {
                "task_id": str(row.id),
                "title": row.title,
                "status": row.status,
                "due_date": row.due_date.isoformat() if row.due_date else None,
            }
            for row in rows
        ]

    def _approve_attestation(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        record_id: uuid.UUID,
    ) -> dict:
        record = (
            self.db.execute(
                select(PolicyAttestationRecord).where(
                    PolicyAttestationRecord.organization_id == organization_id,
                    PolicyAttestationRecord.id == record_id,
                )
            )
            .scalars()
            .one_or_none()
        )
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attestation record not found")

        if record.user_id != actor_user_id and not RBACService.user_has_permission(
            self.db,
            actor_user_id,
            organization_id,
            "attestations:manage",
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Attestation approval not permitted")

        row = AttestationRecordService(self.db).submit_attestation(
            organization_id,
            record.campaign_id,
            record.user_id,
            actor_user_id,
        )
        return {
            "record_id": str(row.id),
            "campaign_id": str(row.campaign_id),
            "user_id": str(row.user_id),
            "status": row.status,
            "attested_at": row.attested_at.isoformat() if row.attested_at else None,
        }

    def _urgent_action(self, organization_id: uuid.UUID, actor_user_id: uuid.UUID) -> dict:
        sla = SLAService(self.db).check_sla_breaches(organization_id)
        queued_reminders = 0
        pending_record = (
            self.db.execute(
                select(PolicyAttestationRecord)
                .where(
                    PolicyAttestationRecord.organization_id == organization_id,
                    PolicyAttestationRecord.user_id == actor_user_id,
                    PolicyAttestationRecord.status == "pending",
                )
                .order_by(PolicyAttestationRecord.created_at.asc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if pending_record is not None:
            AttestationRecordService(self.db).send_reminder(
                organization_id,
                pending_record.campaign_id,
                pending_record.user_id,
                actor_user_id,
            )
            queued_reminders = 1
        return {
            "sla_response_breached": int(sla.get("response_breached", 0)),
            "sla_resolution_breached": int(sla.get("resolution_breached", 0)),
            "sla_notifications_queued": int(sla.get("notifications_queued", 0)),
            "attestation_reminders_queued": queued_reminders,
        }

    def handle_command(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        platform: str,
        command: str,
        text: str,
        idempotency_key: str | None = None,
    ) -> dict:
        subscription = self._subscription_or_404(organization_id, actor_user_id, platform)

        # Slack (and, in future, other platforms) retries a slash command delivery with
        # the same trigger id if our first response didn't come back in time. Replaying
        # a mutating subcommand (approve/urgent) would double-fire side effects such as
        # re-sending an attestation reminder email, so short-circuit with the stored
        # response for an already-processed idempotency key instead of re-executing it.
        if idempotency_key is not None:
            existing = self.db.execute(
                select(ComplianceBotOutbox).where(
                    ComplianceBotOutbox.subscription_id == subscription.id,
                    ComplianceBotOutbox.idempotency_key == idempotency_key,
                )
            ).scalar_one_or_none()
            if existing is not None:
                details = dict(existing.payload_json or {}).get("details", {})
                return {
                    "platform": platform,
                    "command": (existing.command_text or "").split()[0].lower() if existing.command_text else "",
                    "handled": True,
                    "response_text": existing.content_text,
                    "state_changed": False,
                    "details": details,
                    "replayed": True,
                }

        normalized = text.strip()
        if command.strip() == "/complivibe" and normalized:
            command_text = normalized
        else:
            full = f"{command} {normalized}".strip()
            command_text = full
        command_text = command_text.strip()
        if command_text.startswith("/complivibe"):
            command_text = command_text[len("/complivibe") :].strip()
        if not command_text:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing bot subcommand")

        tokens = command_text.split()
        subcommand = tokens[0].lower()
        details: dict
        state_changed = False
        response_text: str

        if subcommand == "status":
            details = self._status_payload(organization_id, actor_user_id)
            response_text = (
                f"Status: overdue_tasks={details['overdue_tasks']}, "
                f"pending_attestations={details['pending_attestations']}, "
                f"high_risks={details['high_risks']}, "
                f"evidence_needs_review={details['evidence_needs_review']}."
            )
        elif subcommand == "tasks":
            task_rows = self._top_tasks_payload(organization_id, actor_user_id)
            details = {"tasks": task_rows}
            response_text = "No active tasks." if not task_rows else f"Top tasks: {len(task_rows)} item(s) returned."
        elif subcommand == "approve":
            if len(tokens) < 2:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="approve requires an attestation record id")
            try:
                record_id = uuid.UUID(tokens[1])
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid attestation record id") from exc
            details = self._approve_attestation(organization_id=organization_id, actor_user_id=actor_user_id, record_id=record_id)
            state_changed = True
            response_text = f"Attestation record {details['record_id']} marked as {details['status']}."
        elif subcommand == "urgent":
            details = self._urgent_action(organization_id, actor_user_id)
            state_changed = bool(
                details["sla_response_breached"]
                or details["sla_resolution_breached"]
                or details["attestation_reminders_queued"]
            )
            response_text = (
                f"Urgent scan complete: response_breached={details['sla_response_breached']}, "
                f"resolution_breached={details['sla_resolution_breached']}, "
                f"reminders_queued={details['attestation_reminders_queued']}."
            )
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported bot subcommand")

        now = self.utcnow()
        try:
            outbox = self._queue_outbox(
                organization_id=organization_id,
                subscription=subscription,
                message_type="command_response",
                content_text=response_text,
                payload_json={"platform": platform, "details": details},
                command_text=command_text,
                status_value="sent",
                scheduled_for=now,
                sent_at=now,
                idempotency_key=idempotency_key,
            )
        except IntegrityError:
            # A concurrent retry with the same idempotency key raced us here; the
            # mutating work above already happened (or is in flight) - surface it as a
            # replay instead of raising, since the caller (Slack/Teams) will retry again.
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This command is already being processed; retry shortly.",
            ) from None
        AuditService(self.db).write_audit_log(
            action="compliance_bot.command_handled",
            entity_type="compliance_bot_outbox",
            entity_id=outbox.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            after_json={"platform": platform, "subcommand": subcommand, "state_changed": state_changed},
            metadata_json={"source": "api"},
        )
        return {
            "platform": platform,
            "command": subcommand,
            "handled": True,
            "response_text": response_text,
            "state_changed": state_changed,
            "details": details,
            "replayed": False,
        }

    def run_daily_digest_dispatch(self) -> dict:
        now = self.utcnow()
        hhmm = now.strftime("%H:%M")
        rows = (
            self.db.execute(
                select(ComplianceBotSubscription)
                .where(
                    ComplianceBotSubscription.is_active.is_(True),
                    ComplianceBotSubscription.digest_enabled.is_(True),
                    ComplianceBotSubscription.digest_time_utc == hhmm,
                )
                .order_by(ComplianceBotSubscription.organization_id.asc())
            )
            .scalars()
            .all()
        )
        queued = 0
        failed = 0
        for row in rows:
            if row.last_digest_sent_at is not None and row.last_digest_sent_at.date() >= now.date():
                continue
            try:
                with self.db.begin_nested():
                    payload = DigestService(self.db).build_daily_digest(row.organization_id, row.user_id)
                    content_text = (
                        "Daily digest: "
                        f"overdue_tasks={len(payload['overdue_tasks'])}, "
                        f"expiring_evidence={len(payload['expiring_evidence'])}, "
                        f"open_risks={len(payload['open_risks'])}, "
                        f"upcoming_deadlines={len(payload['upcoming_deadlines'])}."
                    )
                    self._queue_outbox(
                        organization_id=row.organization_id,
                        subscription=row,
                        message_type="daily_digest",
                        content_text=content_text,
                        payload_json=payload,
                        command_text=None,
                        status_value="pending",
                        scheduled_for=now,
                    )
                    row.last_digest_sent_at = now
                    AuditService(self.db).write_audit_log(
                        action="compliance_bot.digest_queued",
                        entity_type="compliance_bot_subscription",
                        entity_id=row.id,
                        organization_id=row.organization_id,
                        actor_user_id=None,
                        after_json={"platform": row.platform, "digest_time_utc": row.digest_time_utc},
                        metadata_json={"source": "scheduler"},
                    )
                queued += 1
            except Exception:  # noqa: BLE001 - one broken org/subscription must not block the whole sweep
                failed += 1
                logger.exception(
                    "compliance_bot daily digest dispatch failed for subscription %s (org %s)",
                    row.id,
                    row.organization_id,
                )
        self.db.flush()
        return {
            "processed_subscriptions": len(rows),
            "queued_messages": queued,
            "organizations_checked": len({str(r.organization_id) for r in rows}),
            "state_changes": queued,
            "failed_subscriptions": failed,
        }

    def run_sla_alert_dispatch(self) -> dict:
        now = self.utcnow()
        rows = (
            self.db.execute(
                select(ComplianceBotSubscription)
                .where(
                    ComplianceBotSubscription.is_active.is_(True),
                    ComplianceBotSubscription.sla_alerts_enabled.is_(True),
                )
                .order_by(ComplianceBotSubscription.organization_id.asc())
            )
            .scalars()
            .all()
        )
        queued = 0
        failed = 0
        org_results: dict[uuid.UUID, dict[str, int]] = {}
        for row in rows:
            last_sent = row.last_sla_alert_sent_at
            if last_sent is not None and (now - last_sent).total_seconds() < 3600:
                continue
            try:
                with self.db.begin_nested():
                    if row.organization_id not in org_results:
                        org_results[row.organization_id] = SLAService(self.db).check_sla_breaches(row.organization_id)
                    result = org_results[row.organization_id]
                    if int(result.get("response_breached", 0)) + int(result.get("resolution_breached", 0)) <= 0:
                        continue
                    content_text = (
                        "SLA alert: "
                        f"response_breached={int(result.get('response_breached', 0))}, "
                        f"resolution_breached={int(result.get('resolution_breached', 0))}."
                    )
                    self._queue_outbox(
                        organization_id=row.organization_id,
                        subscription=row,
                        message_type="sla_alert",
                        content_text=content_text,
                        payload_json=result,
                        command_text=None,
                        status_value="pending",
                        scheduled_for=now,
                    )
                    row.last_sla_alert_sent_at = now
                    AuditService(self.db).write_audit_log(
                        action="compliance_bot.sla_alert_queued",
                        entity_type="compliance_bot_subscription",
                        entity_id=row.id,
                        organization_id=row.organization_id,
                        actor_user_id=None,
                        after_json={
                            "response_breached": int(result.get("response_breached", 0)),
                            "resolution_breached": int(result.get("resolution_breached", 0)),
                        },
                        metadata_json={"source": "scheduler"},
                    )
                queued += 1
            except Exception:  # noqa: BLE001 - one broken org/subscription must not block the whole sweep
                failed += 1
                logger.exception(
                    "compliance_bot sla alert dispatch failed for subscription %s (org %s)",
                    row.id,
                    row.organization_id,
                )
        self.db.flush()
        return {
            "processed_subscriptions": len(rows),
            "queued_messages": queued,
            "organizations_checked": len(org_results),
            "state_changes": queued + sum(
                int(v.get("response_breached", 0)) + int(v.get("resolution_breached", 0)) for v in org_results.values()
            ),
            "failed_subscriptions": failed,
        }

    def list_outbox(self, organization_id: uuid.UUID, user_id: uuid.UUID, platform: str, limit: int) -> list[ComplianceBotOutbox]:
        sub = self._subscription_or_404(organization_id, user_id, platform)
        return (
            self.db.execute(
                select(ComplianceBotOutbox)
                .where(
                    ComplianceBotOutbox.organization_id == organization_id,
                    ComplianceBotOutbox.subscription_id == sub.id,
                )
                .order_by(ComplianceBotOutbox.created_at.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
