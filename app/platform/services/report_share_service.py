from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.audit_log import AuditLog
from app.models.risk import Risk
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
