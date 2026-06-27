import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.services.email_template_service import EmailTemplateService
from app.models.email_outbox import EmailOutbox
from app.models.organization import Organization
from app.models.org_email_config import OrgEmailConfig
from app.privacy.services.email_config_service import EmailConfigService
from app.services.email_service import EmailService


class EmailFlushService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def flush_outbox(self, org_id: uuid.UUID, db: Session, limit: int = 50) -> dict:
        _ = db
        config = self.db.execute(
            select(OrgEmailConfig).where(
                OrgEmailConfig.organization_id == org_id,
                OrgEmailConfig.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if config is None:
            return {"sent": 0, "failed": 0, "skipped": 1}

        creds = EmailConfigService.decrypt_config(config.config_json)
        from app.compliance.services.email_delivery_service import SESEmailDeliveryService

        sender = SESEmailDeliveryService(
            aws_access_key_id=creds["aws_access_key_id"],
            aws_secret_access_key=creds["aws_secret_access_key"],
            region=creds["region"],
            from_address=creds["from_address"],
        )

        now = self.utcnow()
        rows = self.db.execute(
            select(EmailOutbox)
            .where(
                EmailOutbox.organization_id == org_id,
                EmailOutbox.status.in_(["pending", "failed"]),
                (EmailOutbox.scheduled_at.is_(None) | (EmailOutbox.scheduled_at <= now)),
                (EmailOutbox.next_attempt_at.is_(None) | (EmailOutbox.next_attempt_at <= now)),
            )
            .order_by(EmailOutbox.queued_at.asc())
            .limit(max(1, min(limit, 500)))
        ).scalars().all()

        sent = 0
        failed = 0
        skipped = 0
        email_service = EmailService(self.db)
        template_service = EmailTemplateService()
        org = self.db.execute(select(Organization).where(Organization.id == org_id)).scalar_one_or_none()
        org_name = org.name if org is not None else "Your Organization"

        for row in rows:
            if row.status in {"sent", "cancelled", "dead_letter", "skipped"}:
                skipped += 1
                continue

            subject = row.subject
            html_body = row.body_html or row.body_text
            if row.template_name and isinstance(row.template_context, dict):
                context = dict(row.template_context or {})
                if "subject" not in context and subject:
                    context["subject"] = subject
                try:
                    rendered_subject, rendered_html = template_service.render(
                        row.template_name,
                        context,
                        org_name=org_name,
                    )
                    subject = rendered_subject
                    html_body = rendered_html
                except Exception:
                    # Template rendering failures should not block fallback delivery.
                    pass

            ok = sender.send(
                to=row.recipient_email,
                subject=subject,
                html_body=html_body,
                text_body=row.body_text,
            )
            row.last_attempt_at = now
            row.attempt_count = int(row.attempt_count or 0) + 1
            row.provider = "ses"

            if ok:
                previous = row.status
                row.status = "sent"
                row.sent_at = now
                row.failed_at = None
                row.last_error = None
                row.next_attempt_at = None
                sent += 1
                email_service.add_delivery_event(
                    organization_id=org_id,
                    email_outbox_id=row.id,
                    event_type="email.ses_sent",
                    status_from=previous,
                    status_to=row.status,
                    details_json={"provider": "ses"},
                    created_by_user_id=None,
                )
            else:
                previous = row.status
                row.status = "failed"
                row.failed_at = now
                row.last_error = "SES delivery failed"
                row.next_attempt_at = now + timedelta(minutes=5)
                failed += 1
                email_service.add_delivery_event(
                    organization_id=org_id,
                    email_outbox_id=row.id,
                    event_type="email.ses_failed",
                    status_from=previous,
                    status_to=row.status,
                    details_json={"provider": "ses"},
                    created_by_user_id=None,
                )

        return {"sent": sent, "failed": failed, "skipped": skipped}


def run_email_outbox_flush_sweep(db: Session, limit_per_org: int = 50) -> dict:
    service = EmailFlushService(db)
    org_ids = db.execute(select(OrgEmailConfig.organization_id).where(OrgEmailConfig.is_active.is_(True))).scalars().all()

    total_sent = 0
    total_failed = 0
    total_skipped = 0
    for org_id in org_ids:
        result = service.flush_outbox(org_id, db, limit=limit_per_org)
        total_sent += int(result.get("sent", 0))
        total_failed += int(result.get("failed", 0))
        total_skipped += int(result.get("skipped", 0))

    return {
        "orgs_processed": len(org_ids),
        "sent": total_sent,
        "failed": total_failed,
        "skipped": total_skipped,
    }
