import uuid
from datetime import UTC, date, datetime, time, timedelta

from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.compliance.services.email_template_service import EmailTemplateService
from app.models.compliance_deadline import ComplianceDeadline
from app.models.digest_config import DigestConfig
from app.models.email_outbox import EmailOutbox
from app.models.evidence_item import EvidenceItem
from app.models.issue import Issue
from app.models.org_email_config import OrgEmailConfig
from app.models.organization import Organization
from app.models.risk import Risk
from app.models.task import Task
from app.models.user import User
from app.privacy.services.notification_preference_service import NotificationPreferenceService
from app.services.audit_service import AuditService


class DigestService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _parse_send_time(value: str) -> str:
        try:
            parts = value.split(":")
            hh = int(parts[0])
            mm = int(parts[1])
            _ = time(hour=hh, minute=mm)
            return f"{hh:02d}:{mm:02d}"
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid send_time_utc format") from exc

    def get_or_create_configs(self, org_id: uuid.UUID, user_id: uuid.UUID) -> list[DigestConfig]:
        now = self.utcnow()
        defaults = [
            ("daily", "08:00", None),
            ("weekly", "08:00", 0),
        ]
        for digest_type, send_time_utc, send_day_of_week in defaults:
            row = self.db.execute(
                select(DigestConfig).where(
                    DigestConfig.organization_id == org_id,
                    DigestConfig.user_id == user_id,
                    DigestConfig.digest_type == digest_type,
                )
            ).scalar_one_or_none()
            if row is None:
                self.db.add(
                    DigestConfig(
                        organization_id=org_id,
                        user_id=user_id,
                        digest_type=digest_type,
                        is_enabled=True,
                        send_time_utc=send_time_utc,
                        send_day_of_week=send_day_of_week,
                        last_sent_at=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
        self.db.flush()
        return self.db.execute(
            select(DigestConfig)
            .where(DigestConfig.organization_id == org_id, DigestConfig.user_id == user_id)
            .order_by(DigestConfig.digest_type.asc())
        ).scalars().all()

    def update_daily_config(self, org_id: uuid.UUID, user_id: uuid.UUID, is_enabled: bool, send_time_utc: str) -> DigestConfig:
        self.get_or_create_configs(org_id, user_id)
        row = self.db.execute(
            select(DigestConfig).where(
                DigestConfig.organization_id == org_id,
                DigestConfig.user_id == user_id,
                DigestConfig.digest_type == "daily",
            )
        ).scalar_one()
        row.is_enabled = bool(is_enabled)
        row.send_time_utc = self._parse_send_time(send_time_utc)
        row.updated_at = self.utcnow()
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="digest.config_updated",
            entity_type="digest_config",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"digest_type": row.digest_type, "is_enabled": row.is_enabled, "send_time_utc": row.send_time_utc},
            metadata_json={"source": "api"},
        )
        return row

    def update_weekly_config(self, org_id: uuid.UUID, user_id: uuid.UUID, is_enabled: bool, send_day_of_week: int) -> DigestConfig:
        self.get_or_create_configs(org_id, user_id)
        row = self.db.execute(
            select(DigestConfig).where(
                DigestConfig.organization_id == org_id,
                DigestConfig.user_id == user_id,
                DigestConfig.digest_type == "weekly",
            )
        ).scalar_one()
        row.is_enabled = bool(is_enabled)
        row.send_day_of_week = int(send_day_of_week)
        row.updated_at = self.utcnow()
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="digest.config_updated",
            entity_type="digest_config",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"digest_type": row.digest_type, "is_enabled": row.is_enabled, "send_day_of_week": row.send_day_of_week},
            metadata_json={"source": "api"},
        )
        return row

    def build_daily_digest(self, org_id: uuid.UUID, user_id: uuid.UUID, db: Session | None = None) -> dict:
        _db = db or self.db
        now = self.utcnow()
        today = now.date()

        overdue_tasks = _db.execute(
            select(Task).where(
                Task.organization_id == org_id,
                Task.owner_user_id == user_id,
                Task.due_date.is_not(None),
                Task.due_date < now,
                Task.status.notin_(["completed", "cancelled"]),
            ).order_by(Task.due_date.asc()).limit(10)
        ).scalars().all()

        expiring_evidence = _db.execute(
            select(EvidenceItem).where(
                EvidenceItem.organization_id == org_id,
                EvidenceItem.valid_until.is_not(None),
                EvidenceItem.valid_until >= datetime.combine(today, time.min, tzinfo=UTC),
                EvidenceItem.valid_until <= datetime.combine(today + timedelta(days=30), time.max, tzinfo=UTC),
                EvidenceItem.status != "expired",
            ).order_by(EvidenceItem.valid_until.asc()).limit(10)
        ).scalars().all()

        open_risks = _db.execute(
            select(Risk).where(
                Risk.organization_id == org_id,
                Risk.owner_user_id == user_id,
                Risk.status.notin_(["closed", "accepted"]),
                Risk.severity.in_(["critical", "high"]),
            ).order_by(Risk.severity.asc()).limit(5)
        ).scalars().all()

        upcoming_deadlines = _db.execute(
            select(ComplianceDeadline).where(
                ComplianceDeadline.organization_id == org_id,
                ComplianceDeadline.owner_user_id == user_id,
                ComplianceDeadline.due_date >= today,
                ComplianceDeadline.due_date <= today + timedelta(days=14),
                ComplianceDeadline.status.notin_(["completed", "cancelled"]),
            ).order_by(ComplianceDeadline.due_date.asc()).limit(10)
        ).scalars().all()

        return {
            "digest_type": "daily",
            "generated_at": now.isoformat(),
            "user_id": str(user_id),
            "overdue_tasks": [
                {
                    "id": str(t.id),
                    "title": t.title,
                    "due_date": str(t.due_date.date()) if t.due_date else None,
                    "days_overdue": max(0, (today - t.due_date.date()).days) if t.due_date else 0,
                }
                for t in overdue_tasks
            ],
            "expiring_evidence": [
                {
                    "id": str(e.id),
                    "title": e.title,
                    "valid_until": str(e.valid_until.date()) if e.valid_until else None,
                    "days_remaining": max(0, (e.valid_until.date() - today).days) if e.valid_until else 0,
                }
                for e in expiring_evidence
            ],
            "open_risks": [
                {
                    "id": str(r.id),
                    "title": r.title,
                    "severity": r.severity,
                }
                for r in open_risks
            ],
            "upcoming_deadlines": [
                {
                    "id": str(d.id),
                    "title": d.title,
                    "due_date": str(d.due_date),
                    "days_remaining": (d.due_date - today).days,
                }
                for d in upcoming_deadlines
            ],
        }

    def build_weekly_digest(self, org_id: uuid.UUID, user_id: uuid.UUID, db: Session | None = None) -> dict:
        _db = db or self.db
        daily = self.build_daily_digest(org_id, user_id, _db)

        now = self.utcnow()
        week_ago = now - timedelta(days=7)
        today = now.date()
        month_end = date(today.year, today.month, 28) + timedelta(days=4)
        month_end = month_end - timedelta(days=month_end.day)

        new_issues = int(
            _db.execute(
                select(func.count(Issue.id)).where(
                    Issue.organization_id == org_id,
                    Issue.created_at >= week_ago,
                    Issue.deleted_at.is_(None),
                )
            ).scalar_one()
            or 0
        )

        obligations_due = int(
            _db.execute(
                select(func.count(ComplianceDeadline.id)).where(
                    ComplianceDeadline.organization_id == org_id,
                    ComplianceDeadline.due_date <= month_end,
                    ComplianceDeadline.due_date >= today,
                    ComplianceDeadline.status.notin_(["completed", "cancelled"]),
                )
            ).scalar_one()
            or 0
        )

        return {
            **daily,
            "digest_type": "weekly",
            "new_issues_this_week": new_issues,
            "obligations_due_this_month": obligations_due,
        }

    def send_digest(self, org_id: uuid.UUID, user_id: uuid.UUID, digest_type: str, db: Session | None = None) -> bool:
        _db = db or self.db
        if digest_type not in {"daily", "weekly"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid digest type")

        if not NotificationPreferenceService(_db).should_notify(org_id, user_id, f"digest_{digest_type}"):
            return False

        cfg_active = _db.execute(
            select(OrgEmailConfig).where(
                OrgEmailConfig.organization_id == org_id,
                OrgEmailConfig.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if cfg_active is None:
            return False

        user = _db.get(User, user_id)
        if user is None or not user.email:
            return False
        org = _db.get(Organization, org_id)

        content = self.build_daily_digest(org_id, user_id, _db) if digest_type == "daily" else self.build_weekly_digest(org_id, user_id, _db)

        template_svc = EmailTemplateService()
        subject, html = template_svc.render(
            f"digest_{digest_type}.html",
            {
                "subject": f"Your {digest_type.title()} CompliVibe Digest",
                "user_name": user.full_name or user.email,
                **content,
            },
            org_name=org.name if org else "CompliVibe",
        )

        now = self.utcnow()
        _db.add(
            EmailOutbox(
                organization_id=org_id,
                template_id=None,
                event_type=f"digest.{digest_type}",
                template_name=f"digest_{digest_type}.html",
                template_context={
                    "subject": subject,
                    "user_name": user.full_name or user.email,
                    **content,
                },
                recipient_email=user.email,
                recipient_user_id=user.id,
                subject=subject,
                body_text=f"Your {digest_type} CompliVibe digest is ready.",
                body_html=html,
                status="pending",
                priority="normal",
                scheduled_at=None,
                queued_at=now,
                sent_at=None,
                failed_at=None,
                cancelled_at=None,
                locked_at=None,
                locked_by=None,
                lock_expires_at=None,
                last_attempt_at=None,
                next_attempt_at=None,
                dead_lettered_at=None,
                attempt_count=0,
                max_attempts=3,
                last_error=None,
                provider=None,
                provider_message_id=None,
                metadata_json={"source": "digest", "digest_type": digest_type},
                worker_metadata_json=None,
                created_by_user_id=None,
            )
        )
        _db.flush()

        AuditService(_db).write_audit_log(
            action="digest.sent",
            entity_type="email_outbox",
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"digest_type": digest_type, "recipient_user_id": str(user_id)},
            metadata_json={"source": "scheduler_or_manual"},
        )
        return True

    def _digest_configs_due(self, digest_type: str, now: datetime) -> list[DigestConfig]:
        rows = self.db.execute(
            select(DigestConfig).where(
                DigestConfig.digest_type == digest_type,
                DigestConfig.is_enabled.is_(True),
            )
        ).scalars().all()
        due: list[DigestConfig] = []
        for row in rows:
            if row.send_time_utc != "08:00":
                continue
            if digest_type == "weekly" and row.send_day_of_week not in (None, 0):
                continue
            if row.last_sent_at is not None and row.last_sent_at.date() >= now.date():
                continue
            due.append(row)
        return due

    def run_daily_digest_send(self) -> dict:
        now = self.utcnow()
        queued = 0
        skipped = 0
        processed = 0
        for row in self._digest_configs_due("daily", now):
            processed += 1
            if self.send_digest(row.organization_id, row.user_id, "daily", self.db):
                row.last_sent_at = now
                row.updated_at = now
                queued += 1
            else:
                skipped += 1
        self.db.flush()
        return {"processed": processed, "queued": queued, "skipped": skipped, "records_processed": processed}

    def run_weekly_digest_send(self) -> dict:
        now = self.utcnow()
        queued = 0
        skipped = 0
        processed = 0
        for row in self._digest_configs_due("weekly", now):
            processed += 1
            if self.send_digest(row.organization_id, row.user_id, "weekly", self.db):
                row.last_sent_at = now
                row.updated_at = now
                queued += 1
            else:
                skipped += 1
        self.db.flush()
        return {"processed": processed, "queued": queued, "skipped": skipped, "records_processed": processed}


def run_daily_digest_send_sweep(db: Session) -> dict:
    return DigestService(db).run_daily_digest_send()


def run_weekly_digest_send_sweep(db: Session) -> dict:
    return DigestService(db).run_weekly_digest_send()
