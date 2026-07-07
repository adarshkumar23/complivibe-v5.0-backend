import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.services.incident_sla_service import resolve_regulatory_sla_hours
from app.compliance.services.ai_drafting_service import AIDraftingService
from app.models.breach_notification import BreachNotification
from app.models.email_outbox import EmailOutbox
from app.models.issue import Issue
from app.models.org_ai_config import OrgAIConfig
from app.models.user import User
from app.services.audit_service import AuditService


class BreachNotificationService:
    ALLOWED_ISSUE_TYPES: set[str] = {"security_incident", "data_loss", "unauthorized_access"}
    ALLOWED_STATUS: set[str] = {"assessing", "notification_due", "regulator_notified", "subjects_notified", "closed"}
    STATUS_TRANSITIONS: dict[str, set[str]] = {
        "assessing": {"notification_due", "closed"},
        "notification_due": {"regulator_notified", "closed"},
        "regulator_notified": {"subjects_notified", "closed"},
        "subjects_notified": {"closed"},
        "closed": set(),
    }

    def __init__(self, db: Session) -> None:
        self.db = db

    ARTICLE33_TEMPLATE = (
        "GDPR Article 33 Notification Draft\n\n"
        "To: {supervisory_authority}\n"
        "Re: Personal Data Breach Notification\n\n"
        "We hereby notify you of a personal data breach that occurred. "
        "Nature of breach: {breach_type}. Approximate number of data subjects affected: "
        "{data_subjects_affected_count}. Categories of data concerned: {special_category_note}. "
        "Likely consequences: {description}. Measures taken: [To be completed by data controller]. "
        "\n\nThis is a draft for human review only."
    )

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _has_text(value: str | None) -> bool:
        return bool((value or "").strip())

    def _get_issue(self, org_id: uuid.UUID, issue_id: uuid.UUID) -> Issue:
        row = self.db.execute(
            select(Issue).where(
                Issue.id == issue_id,
                Issue.organization_id == org_id,
                Issue.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
        return row

    def _get_breach(self, org_id: uuid.UUID, breach_id: uuid.UUID) -> BreachNotification:
        row = self.db.execute(
            select(BreachNotification).where(
                BreachNotification.id == breach_id,
                BreachNotification.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Breach notification not found")
        return row

    def _transition(self, row: BreachNotification, new_status: str) -> None:
        allowed = self.STATUS_TRANSITIONS.get(row.status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid breach transition from {row.status} to {new_status}",
            )
        row.status = new_status

    def breach_context(self, row: BreachNotification, *, now: datetime | None = None) -> dict:
        evaluated_now = now or self.utcnow()
        created_at = self._as_utc(row.created_at) or evaluated_now
        age_hours = max(0, int((evaluated_now - created_at).total_seconds() // 3600))

        deadline = self._as_utc(row.regulatory_notification_deadline)
        time_to_deadline_hours: int | None = None
        overdue_by_hours = 0
        if deadline is not None:
            delta_hours = int((deadline - evaluated_now).total_seconds() // 3600)
            time_to_deadline_hours = delta_hours
            if delta_hours < 0:
                overdue_by_hours = abs(delta_hours)

        context_flags: list[str] = []
        if row.regulatory_notification_required:
            if row.regulatory_notified_at is None:
                context_flags.append("regulator_notification_pending")
            if not self._has_text(row.supervisory_authority):
                context_flags.append("supervisory_authority_missing")
            if time_to_deadline_hours is not None:
                if time_to_deadline_hours < 0 and row.regulatory_notified_at is None:
                    context_flags.append("regulatory_deadline_missed")
                elif time_to_deadline_hours <= 6 and row.regulatory_notified_at is None:
                    context_flags.append("regulatory_deadline_approaching")
        if row.article34_required or row.subject_notification_required:
            if row.subjects_notified_at is None:
                context_flags.append("subject_notification_pending")
        if row.special_category_data_involved:
            context_flags.append("special_category_data_involved")
        if (
            row.data_subjects_affected_count is not None
            and row.estimated_affected_count is not None
            and row.data_subjects_affected_count < row.estimated_affected_count
        ):
            context_flags.append("affected_count_below_initial_estimate")
        if row.article34_required and not self._has_text(row.subjects_notification_text):
            context_flags.append("article34_notice_text_missing")
        if row.regulatory_notification_required and not self._has_text(row.article33_notification_text):
            context_flags.append("article33_notice_text_missing")

        return {
            "age_hours": age_hours,
            "time_to_deadline_hours": time_to_deadline_hours,
            "overdue_by_hours": overdue_by_hours,
            "context_flags": context_flags,
        }

    def breach_response_payload(self, row: BreachNotification) -> dict:
        context = self.breach_context(row)
        return {
            "id": row.id,
            "organization_id": row.organization_id,
            "issue_id": row.issue_id,
            "breach_type": row.breach_type,
            "personal_data_affected": row.personal_data_affected,
            "estimated_affected_count": row.estimated_affected_count,
            "regulatory_notification_required": row.regulatory_notification_required,
            "regulatory_framework": row.regulatory_framework,
            "regulatory_notification_hours": row.regulatory_notification_hours,
            "regulatory_notification_deadline": row.regulatory_notification_deadline,
            "supervisory_authority": row.supervisory_authority,
            "regulatory_notified_at": row.regulatory_notified_at,
            "subject_notification_required": row.subject_notification_required,
            "subjects_notified_at": row.subjects_notified_at,
            "data_subjects_affected_count": row.data_subjects_affected_count,
            "special_category_data_involved": row.special_category_data_involved,
            "article33_notification_text": row.article33_notification_text,
            "article34_required": row.article34_required,
            "subjects_notification_text": row.subjects_notification_text,
            "dpa_reference_number": row.dpa_reference_number,
            "status": row.status,
            "created_by": row.created_by,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "age_hours": context["age_hours"],
            "time_to_deadline_hours": context["time_to_deadline_hours"],
            "overdue_by_hours": context["overdue_by_hours"],
            "context_flags": context["context_flags"],
        }

    def create_breach_notification(self, org_id: uuid.UUID, issue_id: uuid.UUID, data, created_by: uuid.UUID) -> BreachNotification:
        issue = self._get_issue(org_id, issue_id)
        if issue.issue_type not in self.ALLOWED_ISSUE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Breach notifications can only be created for security_incident, data_loss, or unauthorized_access issues.",
            )

        existing = self.db.execute(
            select(BreachNotification).where(
                BreachNotification.organization_id == org_id,
                BreachNotification.issue_id == issue_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Breach notification already exists for this issue")

        personal_data_affected = bool(data.personal_data_affected or data.breach_type == "personal_data")

        issue_created_at = issue.created_at if issue.created_at.tzinfo is not None else issue.created_at.replace(tzinfo=UTC)
        resolved_hours = resolve_regulatory_sla_hours(data.regulatory_framework, int(data.regulatory_notification_hours))
        deadline = issue_created_at + timedelta(hours=resolved_hours)

        row = BreachNotification(
            organization_id=org_id,
            issue_id=issue_id,
            breach_type=data.breach_type,
            personal_data_affected=personal_data_affected,
            estimated_affected_count=data.estimated_affected_count,
            regulatory_notification_required=data.regulatory_notification_required,
            regulatory_framework=data.regulatory_framework,
            regulatory_notification_hours=resolved_hours,
            regulatory_notification_deadline=deadline,
            supervisory_authority=data.supervisory_authority,
            regulatory_notified_at=None,
            subject_notification_required=data.subject_notification_required,
            subjects_notified_at=None,
            status="assessing",
            created_by=created_by,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="breach_notification.created",
            entity_type="breach_notification",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={"issue_id": str(issue_id), "status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def get_breach_notification(self, org_id: uuid.UUID, breach_id: uuid.UUID) -> BreachNotification:
        return self._get_breach(org_id, breach_id)

    def get_by_issue(self, org_id: uuid.UUID, issue_id: uuid.UUID) -> BreachNotification | None:
        _ = self._get_issue(org_id, issue_id)
        return self.db.execute(
            select(BreachNotification).where(
                BreachNotification.organization_id == org_id,
                BreachNotification.issue_id == issue_id,
            )
        ).scalar_one_or_none()

    def list_breach_notifications(self, org_id: uuid.UUID, *, status_value: str | None = None) -> list[BreachNotification]:
        stmt = select(BreachNotification).where(BreachNotification.organization_id == org_id)
        if status_value is not None:
            if status_value not in self.ALLOWED_STATUS:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid breach status filter")
            stmt = stmt.where(BreachNotification.status == status_value)
        return self.db.execute(stmt.order_by(BreachNotification.created_at.desc())).scalars().all()

    def record_regulator_notification(self, org_id: uuid.UUID, breach_id: uuid.UUID, user_id: uuid.UUID) -> BreachNotification:
        row = self._get_breach(org_id, breach_id)
        if row.status == "closed":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Breach notification is closed")
        if row.status == "assessing":
            self._transition(row, "notification_due")
        self._transition(row, "regulator_notified")
        row.regulatory_notified_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="breach_notification.regulator_notified",
            entity_type="breach_notification",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status, "regulatory_notified_at": row.regulatory_notified_at.isoformat()},
            metadata_json={"source": "api"},
        )
        return row

    def record_subject_notification(self, org_id: uuid.UUID, breach_id: uuid.UUID, user_id: uuid.UUID) -> BreachNotification:
        row = self._get_breach(org_id, breach_id)
        self._transition(row, "subjects_notified")
        row.subjects_notified_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="breach_notification.subjects_notified",
            entity_type="breach_notification",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status, "subjects_notified_at": row.subjects_notified_at.isoformat()},
            metadata_json={"source": "api"},
        )
        return row

    def close_breach(self, org_id: uuid.UUID, breach_id: uuid.UUID, user_id: uuid.UUID) -> BreachNotification:
        row = self._get_breach(org_id, breach_id)
        if (row.subject_notification_required or row.article34_required) and row.subjects_notified_at is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cannot close breach until required Article 34 subject notification is completed",
            )
        if row.regulatory_notification_required and row.regulatory_notified_at is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cannot close breach until required regulator notification is recorded",
            )
        self._transition(row, "closed")
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="breach_notification.closed",
            entity_type="breach_notification",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def update_privacy_fields(self, org_id: uuid.UUID, breach_id: uuid.UUID, data, user_id: uuid.UUID) -> BreachNotification:
        row = self._get_breach(org_id, breach_id)
        payload = data.model_dump(exclude_unset=True) if hasattr(data, "model_dump") else dict(data)

        for key in (
            "data_subjects_affected_count",
            "special_category_data_involved",
            "article33_notification_text",
            "article34_required",
            "subjects_notification_text",
            "dpa_reference_number",
        ):
            if key in payload:
                setattr(row, key, payload[key])

        if payload.get("article34_required") is True:
            row.subject_notification_required = True

        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="breach.privacy_fields_updated",
            entity_type="breach_notification",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={
                "data_subjects_affected_count": row.data_subjects_affected_count,
                "special_category_data_involved": row.special_category_data_involved,
                "article34_required": row.article34_required,
                "dpa_reference_number": row.dpa_reference_number,
            },
            metadata_json={"source": "api"},
        )
        return row

    def _deterministic_article33_draft(self, row: BreachNotification, issue: Issue) -> str:
        special_category_note = "Special category data involved" if row.special_category_data_involved else "No special category data involved"
        return self.ARTICLE33_TEMPLATE.format(
            supervisory_authority=row.supervisory_authority or "Supervisory Authority",
            breach_type=row.breach_type,
            data_subjects_affected_count=row.data_subjects_affected_count or row.estimated_affected_count or "unknown",
            special_category_note=special_category_note,
            description=(issue.description or "Not specified"),
        )

    def generate_article33_draft(self, org_id: uuid.UUID, breach_id: uuid.UUID, user_id: uuid.UUID, db: Session) -> dict:
        row = self._get_breach(org_id, breach_id)
        issue = self._get_issue(org_id, row.issue_id)

        ai_enabled = db.execute(
            select(OrgAIConfig).where(
                OrgAIConfig.organization_id == org_id,
                OrgAIConfig.ai_drafting_enabled.is_(True),
            )
        ).scalar_one_or_none()

        used_ai = False
        draft_text: str
        if ai_enabled is not None:
            try:
                drafting = AIDraftingService(db)
                system_prompt = (
                    "You are a compliance documentation assistant drafting GDPR Article 33 breach notifications. "
                    "Provide a concise, regulator-ready narrative. This is a draft for human review only."
                )
                user_prompt = (
                    f"Draft GDPR Article 33 notification for breach '{issue.title}'. "
                    f"Supervisory authority: {row.supervisory_authority or 'Supervisory Authority'}. "
                    f"Breach type: {row.breach_type}. "
                    f"Affected count: {row.data_subjects_affected_count or row.estimated_affected_count or 'unknown'}. "
                    f"Special category involved: {'yes' if row.special_category_data_involved else 'no'}. "
                    f"Description: {issue.description}."
                )
                draft_text = drafting._call_azure_openai(system_prompt=system_prompt, user_prompt=user_prompt)
                used_ai = True
            except Exception:
                draft_text = self._deterministic_article33_draft(row, issue)
        else:
            draft_text = self._deterministic_article33_draft(row, issue)

        AuditService(self.db).write_audit_log(
            action="breach.article33_draft_generated",
            entity_type="breach_notification",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"used_ai": used_ai},
            metadata_json={"source": "api"},
        )
        return {"draft_text": draft_text, "used_ai": used_ai}

    def record_article33_sent(
        self,
        org_id: uuid.UUID,
        breach_id: uuid.UUID,
        user_id: uuid.UUID,
        sent_to: str | None = None,
    ) -> BreachNotification:
        row = self._get_breach(org_id, breach_id)
        if not row.regulatory_notification_required:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Regulator notification is not required for this breach",
            )
        if row.status == "assessing":
            self._transition(row, "notification_due")
        if row.status == "notification_due":
            self._transition(row, "regulator_notified")
        elif row.status == "regulator_notified":
            pass
        elif row.status in {"subjects_notified", "closed"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Breach notification cannot be regulator-notified from current status")

        row.regulatory_notified_at = self.utcnow()
        if sent_to:
            row.supervisory_authority = sent_to
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="breach.article33_sent",
            entity_type="breach_notification",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={
                "status": row.status,
                "regulatory_notified_at": row.regulatory_notified_at.isoformat(),
                "sent_to": sent_to,
            },
            metadata_json={"source": "api"},
        )
        return row

    def record_subjects_notified_privacy(
        self,
        org_id: uuid.UUID,
        breach_id: uuid.UUID,
        user_id: uuid.UUID,
        count: int | None = None,
    ) -> BreachNotification:
        row = self._get_breach(org_id, breach_id)
        if not (row.subject_notification_required or row.article34_required):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Subject notification is not required for this breach",
            )
        if row.status == "assessing":
            self._transition(row, "notification_due")
        if row.status == "notification_due":
            self._transition(row, "regulator_notified")
        if row.status == "regulator_notified":
            self._transition(row, "subjects_notified")
        elif row.status == "subjects_notified":
            pass
        else:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Breach notification cannot transition to subjects_notified from current status")

        if row.regulatory_notification_required and row.regulatory_notified_at is None:
            row.regulatory_notified_at = self.utcnow()
        row.subjects_notified_at = self.utcnow()
        if count is not None:
            row.data_subjects_affected_count = int(count)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="breach.subjects_notified",
            entity_type="breach_notification",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={
                "status": row.status,
                "subjects_notified_at": row.subjects_notified_at.isoformat(),
                "data_subjects_affected_count": row.data_subjects_affected_count,
            },
            metadata_json={"source": "api"},
        )
        return row

    def _queue_warning(self, issue: Issue, breach: BreachNotification) -> bool:
        owner = self.db.execute(select(User).where(User.id == issue.owner_id)).scalar_one_or_none()
        if owner is None or not owner.email:
            return False

        now = self.utcnow()
        self.db.add(
            EmailOutbox(
                organization_id=issue.organization_id,
                template_id=None,
                event_type="breach_notification.deadline_warning",
                recipient_email=owner.email,
                recipient_user_id=owner.id,
                subject=f"Breach notification deadline approaching: {issue.title}",
                body_text=(
                    f"Issue: {issue.title}\n"
                    f"Breach type: {breach.breach_type}\n"
                    f"Regulatory framework: {breach.regulatory_framework}\n"
                    f"Deadline: {breach.regulatory_notification_deadline.isoformat() if breach.regulatory_notification_deadline else 'N/A'}"
                ),
                body_html=None,
                status="pending",
                priority="high",
                scheduled_at=None,
                queued_at=now,
                attempt_count=0,
                max_attempts=3,
                metadata_json={"source": "breach_notification", "breach_id": str(breach.id)},
                created_by_user_id=breach.created_by,
            )
        )
        return True

    def sweep_breach_deadlines(self) -> dict[str, int]:
        now = self.utcnow()
        window = now + timedelta(hours=6)

        rows = self.db.execute(
            select(BreachNotification, Issue)
            .join(Issue, Issue.id == BreachNotification.issue_id)
            .where(
                BreachNotification.regulatory_notification_required.is_(True),
                BreachNotification.regulatory_notified_at.is_(None),
                BreachNotification.regulatory_notification_deadline.is_not(None),
                BreachNotification.regulatory_notification_deadline <= window,
                BreachNotification.status.notin_(["regulator_notified", "subjects_notified", "closed"]),
                Issue.deleted_at.is_(None),
            )
        ).all()

        warned = 0
        transitioned = 0

        for breach, issue in rows:
            if self._queue_warning(issue, breach):
                warned += 1
            if breach.status != "notification_due":
                self._transition(breach, "notification_due")
                transitioned += 1

            AuditService(self.db).write_audit_log(
                action="breach_notification.deadline_warned",
                entity_type="breach_notification",
                entity_id=breach.id,
                organization_id=breach.organization_id,
                actor_user_id=None,
                after_json={"status": breach.status, "deadline": breach.regulatory_notification_deadline.isoformat() if breach.regulatory_notification_deadline else None},
                metadata_json={"source": "scheduler"},
            )

        self.db.flush()
        return {"warned": warned, "transitioned": transitioned}


def run_daily_breach_notification_deadline_sweep(db: Session) -> dict[str, int]:
    return BreachNotificationService(db).sweep_breach_deadlines()
