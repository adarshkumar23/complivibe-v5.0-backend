import re
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.email_delivery_event import EmailDeliveryEvent
from app.models.email_outbox import EmailOutbox
from app.models.email_template import EmailTemplate
from app.privacy.services.notification_preference_service import NotificationPreferenceService

VAR_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


class EmailService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _extract_variables(template: str) -> set[str]:
        return set(VAR_PATTERN.findall(template or ""))

    @staticmethod
    def _validate_allowed_variables(allowed_variables: list[str], used_variables: set[str], provided_variables: dict) -> None:
        allowed = set(allowed_variables or [])
        if not used_variables.issubset(allowed):
            unknown = sorted(used_variables - allowed)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Template uses variables not in allowed_variables_json: {', '.join(unknown)}",
            )

        unexpected = sorted(set(provided_variables.keys()) - allowed)
        if unexpected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown variables provided: {', '.join(unexpected)}",
            )

    def render_template(self, template: EmailTemplate, variables: dict[str, str | int | float | bool | None]) -> dict[str, str | None]:
        subject_vars = self._extract_variables(template.subject_template)
        text_vars = self._extract_variables(template.body_text_template)
        html_vars = self._extract_variables(template.body_html_template or "")
        used = subject_vars | text_vars | html_vars

        self._validate_allowed_variables(template.allowed_variables_json, used, variables)

        missing = sorted(var for var in used if var not in variables)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing required template variables: {', '.join(missing)}",
            )

        def replace(tpl: str | None) -> str | None:
            if tpl is None:
                return None

            def repl(match: re.Match[str]) -> str:
                key = match.group(1)
                value = variables.get(key)
                return "" if value is None else str(value)

            return VAR_PATTERN.sub(repl, tpl)

        return {
            "subject": replace(template.subject_template),
            "body_text": replace(template.body_text_template),
            "body_html": replace(template.body_html_template),
        }

    def resolve_template_for_org(
        self,
        *,
        organization_id: uuid.UUID,
        template_id: uuid.UUID | None,
        template_key: str | None,
    ) -> EmailTemplate:
        if template_id is None and template_key is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="template_id or template_key is required")
        if template_id is not None and template_key is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide template_id or template_key, not both")

        if template_id is not None:
            template = self.db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id)).scalar_one_or_none()
            if template is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email template not found")
            if template.organization_id not in (None, organization_id):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email template not found")
            if template.status != "active":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email template is not active")
            return template

        stmt = (
            select(EmailTemplate)
            .where(
                and_(
                    EmailTemplate.template_key == template_key,
                    EmailTemplate.status == "active",
                    or_(EmailTemplate.organization_id == organization_id, EmailTemplate.organization_id.is_(None)),
                )
            )
            .order_by(EmailTemplate.organization_id.desc().nulls_last(), EmailTemplate.version.desc())
        )
        template = self.db.execute(stmt).scalars().first()
        if template is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email template not found")
        return template

    def add_delivery_event(
        self,
        *,
        organization_id: uuid.UUID | None,
        email_outbox_id: uuid.UUID,
        event_type: str,
        status_from: str | None,
        status_to: str | None,
        details_json: dict | None,
        created_by_user_id: uuid.UUID | None,
    ) -> EmailDeliveryEvent:
        event = EmailDeliveryEvent(
            organization_id=organization_id,
            email_outbox_id=email_outbox_id,
            event_type=event_type,
            status_from=status_from,
            status_to=status_to,
            details_json=details_json,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(event)
        self.db.flush()
        return event

    def queue_email(
        self,
        *,
        organization_id: uuid.UUID,
        template: EmailTemplate,
        event_type: str,
        recipient_email: str,
        recipient_user_id: uuid.UUID | None,
        priority: str,
        scheduled_at: datetime | None,
        metadata_json: dict | None,
        created_by_user_id: uuid.UUID,
        variables_json: dict,
        initial_status: str,
        notification_type: str | None = None,
        severity: str | None = None,
    ) -> EmailOutbox:
        effective_notification_type = notification_type or template.template_key or event_type
        effective_severity = severity
        if effective_severity is None and isinstance(metadata_json, dict):
            maybe_severity = metadata_json.get("severity")
            if isinstance(maybe_severity, str):
                effective_severity = maybe_severity

        suppressed_by_preference = False
        if recipient_user_id is not None:
            suppressed_by_preference = not NotificationPreferenceService(self.db).should_notify(
                organization_id,
                recipient_user_id,
                effective_notification_type,
                severity=effective_severity,
            )

        rendered = self.render_template(template, variables_json)
        queued_at = self._now()
        target_status = "skipped" if suppressed_by_preference else initial_status
        outbox = EmailOutbox(
            organization_id=organization_id,
            template_id=template.id,
            event_type=event_type,
            template_name=None,
            template_context=None,
            recipient_email=recipient_email,
            recipient_user_id=recipient_user_id,
            subject=str(rendered["subject"]),
            body_text=str(rendered["body_text"]),
            body_html=rendered["body_html"],
            status=target_status,
            priority=priority,
            scheduled_at=scheduled_at,
            queued_at=queued_at,
            attempt_count=0,
            max_attempts=3,
            metadata_json=metadata_json,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(outbox)
        self.db.flush()

        self.add_delivery_event(
            organization_id=organization_id,
            email_outbox_id=outbox.id,
            event_type="skipped_by_preference" if suppressed_by_preference else "queued",
            status_from=None,
            status_to=outbox.status,
            details_json={
                "event_type": event_type,
                "notification_type": effective_notification_type,
                "suppressed_by_preference": suppressed_by_preference,
            },
            created_by_user_id=created_by_user_id,
        )

        return outbox
