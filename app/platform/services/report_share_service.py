from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.audit_log import AuditLog
from app.models.compliance_deadline import ComplianceDeadline
from app.models.control import Control
from app.models.evidence_item import EvidenceItem
from app.models.framework import Framework
from app.models.organization_framework import OrganizationFramework
from app.models.risk import Risk
from app.models.task import Task
from app.models.shared_report_link import SharedReportLink
from app.privacy.services.ropa_service import RopaService
from app.services.audit_service import AuditService


MAX_FAILED_PASSWORD_ATTEMPTS = 5
PASSWORD_LOCKOUT_MINUTES = 15


class ReportShareService:
    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def create_share_link(
        self,
        org_id: uuid.UUID,
        created_by: uuid.UUID,
        report_type: str,
        report_params: dict,
        db: Session,
        expires_hours: int = 168,
        password: str | None = None,
        max_views: int | None = None,
        recipient_email: str | None = None,
        watermark_text: str | None = None,
        base_url: str | None = None,
    ) -> dict:
        token = secrets.token_urlsafe(48)
        password_hash = hashlib.sha256(password.encode()).hexdigest() if password else None

        if not watermark_text and recipient_email:
            watermark_text = f"Shared with {recipient_email} - Confidential - {self.utcnow().strftime('%Y-%m-%d')}"

        expires_at = self.utcnow() + timedelta(hours=expires_hours)
        link = SharedReportLink(
            organization_id=org_id,
            created_by=created_by,
            report_type=report_type,
            report_params=report_params,
            token=token,
            password_hash=password_hash,
            expires_at=expires_at,
            max_views=max_views,
            recipient_email=recipient_email,
            watermark_text=watermark_text,
        )
        db.add(link)
        db.flush()

        AuditService(db).write_audit_log(
            action="report.share_link_created",
            entity_type="shared_report_links",
            organization_id=org_id,
            actor_user_id=created_by,
            entity_id=link.id,
            metadata_json={
                "report_type": report_type,
                "expires_at": expires_at.isoformat(),
                "password_protected": bool(password),
                "recipient": recipient_email,
            },
        )

        settings = get_settings()
        resolved_base = (base_url or settings.BASE_URL).rstrip("/")
        return self.share_link_response_payload(
            link=link,
            share_url=f"{resolved_base}/api/v1/reports/shared/{token}",
        )

    def access_shared_report(self, token: str, db: Session, password: str | None = None) -> dict:
        link = self._get_active_link(token, db)
        self._ensure_link_accessible(link, enforce_view_cap=True)

        now = self.utcnow()
        self._verify_password(link, password, db)

        link.view_count += 1
        link.last_viewed_at = now
        db.flush()

        data = self._generate_report(
            org_id=link.organization_id,
            report_type=link.report_type,
            report_params=link.report_params or {},
            db=db,
        )

        context = self.link_context(link)
        AuditService(db).write_audit_log(
            action="report.shared_accessed",
            entity_type="shared_report_links",
            entity_id=link.id,
            organization_id=link.organization_id,
            actor_user_id=None,
            after_json={
                "view_count": link.view_count,
                "views_remaining": context["views_remaining"],
                "context_flags": context["context_flags"],
            },
        )

        return {
            "report_type": link.report_type,
            "watermark": link.watermark_text,
            "expires_at": link.expires_at.isoformat(),
            "views_remaining": context["views_remaining"],
            "generated_at": self.utcnow().isoformat(),
            "context_flags": context["context_flags"],
            "data": data,
        }

    def verify_password(self, token: str, db: Session, password: str | None = None) -> bool:
        link = self._get_active_link(token, db)
        self._ensure_link_accessible(link, enforce_view_cap=True)
        try:
            self._verify_password(link, password, db)
        except HTTPException as exc:
            # Propagate rate-limit / lockout responses so the API can return 429.
            if exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
                raise
            return False
        return True

    def list_org_links(self, org_id: uuid.UUID, db: Session) -> list[SharedReportLink]:
        return (
            db.execute(
                select(SharedReportLink)
                .where(
                    SharedReportLink.organization_id == org_id,
                    SharedReportLink.deleted_at.is_(None),
                )
                .order_by(SharedReportLink.created_at.desc())
            )
            .scalars()
            .all()
        )

    def list_org_link_payloads(self, org_id: uuid.UUID, db: Session) -> list[dict]:
        rows = self.list_org_links(org_id, db)
        return [self.share_link_list_payload(row) for row in rows]

    def revoke_link(self, org_id: uuid.UUID, link_id: uuid.UUID, user_id: uuid.UUID, db: Session) -> None:
        link = db.execute(
            select(SharedReportLink).where(
                SharedReportLink.id == link_id,
                SharedReportLink.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if link is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
        if link.deleted_at is not None or not link.is_active:
            return

        now = self.utcnow()
        link.is_active = False
        link.deleted_at = now
        db.flush()

        AuditService(db).write_audit_log(
            action="report.share_link_revoked",
            entity_type="shared_report_links",
            organization_id=org_id,
            actor_user_id=user_id,
            entity_id=link_id,
        )

    def _as_utc(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def link_context(self, link: SharedReportLink) -> dict:
        now = self.utcnow()
        expires_at = self._as_utc(link.expires_at) or now
        locked_until = self._as_utc(link.locked_until)
        is_expired = expires_at < now
        views_remaining = (link.max_views - link.view_count) if link.max_views is not None else None
        is_view_cap_reached = views_remaining is not None and views_remaining <= 0
        is_locked = locked_until is not None and locked_until > now
        expires_in_hours = round((expires_at - now).total_seconds() / 3600.0, 2)

        flags: list[str] = []
        if link.password_hash:
            flags.append("password_protected")
        if is_expired:
            flags.append("share_link_expired")
        if is_view_cap_reached:
            flags.append("share_link_view_cap_reached")
        if is_locked:
            flags.append("share_link_password_locked")
        if 0 < expires_in_hours <= 24:
            flags.append("share_link_expires_within_24h")
        if views_remaining is not None and views_remaining <= 1 and views_remaining >= 0:
            flags.append("share_link_near_view_cap")
        if link.deleted_at is not None or not link.is_active:
            flags.append("share_link_revoked")

        return {
            "is_expired": is_expired,
            "views_remaining": views_remaining,
            "is_view_cap_reached": is_view_cap_reached,
            "is_locked": is_locked,
            "expires_in_hours": expires_in_hours,
            "password_protected": bool(link.password_hash),
            "context_flags": flags,
        }

    def share_link_response_payload(self, link: SharedReportLink, *, share_url: str) -> dict:
        context = self.link_context(link)
        return {
            "share_id": link.id,
            "share_url": share_url,
            "token": link.token,
            "expires_at": link.expires_at,
            "password_protected": context["password_protected"],
            "max_views": link.max_views,
            "watermark_text": link.watermark_text,
            "expires_in_hours": context["expires_in_hours"],
            "context_flags": context["context_flags"],
            "warning": "Store this URL securely. It grants access to the report.",
        }

    def share_link_list_payload(self, link: SharedReportLink) -> dict:
        context = self.link_context(link)
        return {
            "id": link.id,
            "report_type": link.report_type,
            "expires_at": link.expires_at,
            "view_count": link.view_count,
            "max_views": link.max_views,
            "views_remaining": context["views_remaining"],
            "is_active": link.is_active,
            "is_expired": context["is_expired"],
            "is_locked": context["is_locked"],
            "password_protected": context["password_protected"],
            "expires_in_hours": context["expires_in_hours"],
            "context_flags": context["context_flags"],
            "recipient_email": link.recipient_email,
            "created_at": link.created_at,
        }

    def _ensure_link_accessible(self, link: SharedReportLink, *, enforce_view_cap: bool) -> None:
        context = self.link_context(link)
        if context["is_expired"]:
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="This report link has expired")
        if enforce_view_cap and context["is_view_cap_reached"]:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="This report link has reached its maximum view count",
            )

    def _get_active_link(self, token: str, db: Session) -> SharedReportLink:
        link = db.execute(
            select(SharedReportLink).where(
                SharedReportLink.token == token,
                SharedReportLink.is_active.is_(True),
                SharedReportLink.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if link is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report link not found or expired")
        return link

    def _verify_password(self, link: SharedReportLink, password: str | None, db: Session) -> None:
        if not link.password_hash:
            return

        now = self.utcnow()
        if link.locked_until is not None:
            compare_now = now if link.locked_until.tzinfo is not None else now.replace(tzinfo=None)
            if link.locked_until > compare_now:
                retry_after = int((link.locked_until - compare_now).total_seconds())
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many failed password attempts for this share link. Please try again later.",
                    headers={"Retry-After": str(max(1, retry_after))},
                )
            # Lockout has expired; reset the counter for a fresh window.
            link.failed_password_attempt_count = 0
            link.locked_until = None

        if not password:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="This report is password protected",
                headers={"WWW-Authenticate": "password"},
            )

        provided_hash = hashlib.sha256(password.encode()).hexdigest()
        if hmac.compare_digest(provided_hash, link.password_hash):
            # Successful authentication resets the failure window.
            link.failed_password_attempt_count = 0
            link.locked_until = None
            return

        link.failed_password_attempt_count += 1
        if link.failed_password_attempt_count >= MAX_FAILED_PASSWORD_ATTEMPTS:
            link.locked_until = now + timedelta(minutes=PASSWORD_LOCKOUT_MINUTES)
            AuditService(db).write_audit_log(
                action="report.share_password_lockout",
                entity_type="shared_report_links",
                entity_id=link.id,
                organization_id=link.organization_id,
                actor_user_id=None,
                after_json={
                    "failed_password_attempt_count": link.failed_password_attempt_count,
                    "locked_until": link.locked_until.isoformat(),
                },
            )
        db.flush()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password")

    def _generate_report(self, org_id: uuid.UUID, report_type: str, report_params: dict, db: Session) -> dict:
        if report_type == "risk_register":
            risks = db.execute(
                select(Risk)
                .where(Risk.organization_id == org_id)
                .order_by(Risk.created_at.desc())
            ).scalars().all()
            return {
                "risks": [
                    {
                        "title": risk.title,
                        "severity": risk.severity,
                        "status": risk.status,
                        "treatment_option": getattr(risk, "treatment_option", None),
                    }
                    for risk in risks
                ],
                "total": len(risks),
            }

        if report_type == "gdpr_article30":
            return RopaService(db).generate_article30_report(org_id)

        if report_type == "compliance_summary":
            return {
                "organization_id": str(org_id),
                "report_params": report_params,
                "note": "Full compliance summary - rendered by frontend",
            }

        if report_type == "compliance_one_page_summary":
            active_framework_rows = (
                db.execute(
                    select(Framework.code, Framework.name)
                    .join(OrganizationFramework, OrganizationFramework.framework_id == Framework.id)
                    .where(
                        OrganizationFramework.organization_id == org_id,
                        OrganizationFramework.status == "active",
                    )
                    .order_by(Framework.name.asc())
                )
                .all()
            )
            active_frameworks = [{"code": str(code), "name": str(name)} for code, name in active_framework_rows]

            total_controls = int(
                db.execute(select(func.count(Control.id)).where(Control.organization_id == org_id)).scalar_one()
            )
            implemented_controls = int(
                db.execute(
                    select(func.count(Control.id)).where(
                        Control.organization_id == org_id,
                        Control.status.in_(["implemented", "monitoring", "effective"]),
                    )
                ).scalar_one()
            )
            controls_pct = round((implemented_controls / total_controls) * 100, 1) if total_controls > 0 else 0.0

            evidence_total = int(
                db.execute(select(func.count(EvidenceItem.id)).where(EvidenceItem.organization_id == org_id)).scalar_one()
            )
            evidence_fresh = int(
                db.execute(
                    select(func.count(EvidenceItem.id)).where(
                        EvidenceItem.organization_id == org_id,
                        EvidenceItem.freshness_status == "fresh",
                    )
                ).scalar_one()
            )
            evidence_fresh_pct = round((evidence_fresh / evidence_total) * 100, 1) if evidence_total > 0 else 0.0

            open_high_risks = int(
                db.execute(
                    select(func.count(Risk.id)).where(
                        Risk.organization_id == org_id,
                        Risk.status.not_in(["closed", "accepted"]),
                        Risk.severity.in_(["high", "critical"]),
                    )
                ).scalar_one()
            )

            overdue_tasks = int(
                db.execute(
                    select(func.count(Task.id)).where(
                        Task.organization_id == org_id,
                        Task.status.not_in(["completed", "cancelled"]),
                        Task.due_date.is_not(None),
                        Task.due_date < self.utcnow(),
                    )
                ).scalar_one()
            )
            overdue_deadlines = int(
                db.execute(
                    select(func.count(ComplianceDeadline.id)).where(
                        ComplianceDeadline.organization_id == org_id,
                        ComplianceDeadline.status == "overdue",
                    )
                ).scalar_one()
            )

            priorities: list[str] = []
            if overdue_tasks > 0:
                priorities.append(f"{overdue_tasks} overdue task(s) need completion")
            if overdue_deadlines > 0:
                priorities.append(f"{overdue_deadlines} overdue compliance deadline(s) need remediation")
            if open_high_risks > 0:
                priorities.append(f"{open_high_risks} high/critical open risk(s) need treatment")
            if controls_pct < 80:
                priorities.append("Control implementation coverage is below 80%")
            if evidence_fresh_pct < 85:
                priorities.append("Evidence freshness is below 85%")
            if not priorities:
                priorities.append("No critical blockers detected in current compliance snapshot")
            priorities = priorities[:3]

            return {
                "report_kind": "one_page_quick_read",
                "brand_name": report_params.get("brand_name") or "CompliVibe",
                "generated_at": self.utcnow().isoformat(),
                "active_frameworks": active_frameworks,
                "overview": {
                    "framework_count": len(active_frameworks),
                    "controls_implemented_pct": controls_pct,
                    "evidence_fresh_pct": evidence_fresh_pct,
                    "open_high_risks": open_high_risks,
                    "overdue_items_total": overdue_tasks + overdue_deadlines,
                },
                "sections_included": report_params.get("include_sections") or [],
                "top_priorities": priorities,
                "metrics": {
                    "controls": {"total": total_controls, "implemented": implemented_controls},
                    "evidence": {"total": evidence_total, "fresh": evidence_fresh},
                    "tasks": {"overdue": overdue_tasks},
                    "deadlines": {"overdue": overdue_deadlines},
                },
            }

        if report_type == "framework_gap":
            return {
                "framework_id": report_params.get("framework_id"),
                "gap_analysis": "Framework gap data",
            }

        if report_type == "audit_log":
            rows = (
                db.execute(
                    select(AuditLog)
                    .where(AuditLog.organization_id == org_id)
                    .order_by(AuditLog.created_at.desc())
                    .limit(100)
                )
                .scalars()
                .all()
            )
            return {
                "count": len(rows),
                "entries": [
                    {
                        "timestamp": row.created_at.isoformat(),
                        "action": row.action,
                        "entity_type": row.entity_type,
                        "entity_id": str(row.entity_id) if row.entity_id else None,
                    }
                    for row in rows
                ],
            }

        return {"report_type": report_type, "params": report_params}
