from __future__ import annotations

import hashlib
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
        share_url = f"{resolved_base}/api/v1/reports/shared/{token}"
        return {
            "share_id": str(link.id),
            "share_url": share_url,
            "token": token,
            "expires_at": expires_at.isoformat(),
            "password_protected": bool(password),
            "max_views": max_views,
            "watermark_text": watermark_text,
            "warning": "Store this URL securely. It grants access to the report.",
        }

    def access_shared_report(self, token: str, db: Session, password: str | None = None) -> dict:
        link = self._get_active_link(token, db)

        now = self.utcnow()
        compare_now = now if link.expires_at.tzinfo is not None else now.replace(tzinfo=None)
        if link.expires_at < compare_now:
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="This report link has expired")
        if link.max_views is not None and link.view_count >= link.max_views:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="This report link has reached its maximum view count",
            )

        self._verify_password(link, password)

        link.view_count += 1
        link.last_viewed_at = now
        db.flush()

        data = self._generate_report(
            org_id=link.organization_id,
            report_type=link.report_type,
            report_params=link.report_params or {},
            db=db,
        )

        return {
            "report_type": link.report_type,
            "watermark": link.watermark_text,
            "expires_at": link.expires_at.isoformat(),
            "views_remaining": (link.max_views - link.view_count) if link.max_views is not None else None,
            "generated_at": self.utcnow().isoformat(),
            "data": data,
        }

    def verify_password(self, token: str, db: Session, password: str | None = None) -> bool:
        link = self._get_active_link(token, db)
        try:
            self._verify_password(link, password)
        except HTTPException:
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

    def revoke_link(self, org_id: uuid.UUID, link_id: uuid.UUID, user_id: uuid.UUID, db: Session) -> None:
        link = db.execute(
            select(SharedReportLink).where(
                SharedReportLink.id == link_id,
                SharedReportLink.organization_id == org_id,
                SharedReportLink.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if link is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

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

    def _verify_password(self, link: SharedReportLink, password: str | None) -> None:
        if not link.password_hash:
            return
        if not password:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="This report is password protected",
                headers={"WWW-Authenticate": "password"},
            )
        provided_hash = hashlib.sha256(password.encode()).hexdigest()
        if provided_hash != link.password_hash:
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
