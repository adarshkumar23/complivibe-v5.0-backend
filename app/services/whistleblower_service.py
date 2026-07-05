from __future__ import annotations

import hashlib
import secrets
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.whistleblower import WhistleblowerMessage, WhistleblowerReport
from app.services.audit_service import AuditService

# Valid forward transitions for report status. A status may not transition to
# itself via this map (no-op updates are rejected as invalid transitions too,
# by omission) except where explicitly listed.
_VALID_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "submitted": {"under_review", "investigating", "dismissed"},
    "under_review": {"investigating", "resolved", "closed", "dismissed"},
    "investigating": {"resolved", "closed", "dismissed"},
    "resolved": {"closed"},
    "closed": set(),
    "dismissed": set(),
}


class WhistleblowerService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def generate_tracking_code() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def generate_anonymous_id() -> str:
        return secrets.token_urlsafe(24)

    @staticmethod
    def hash_tracking_code(code: str) -> str:
        return hashlib.sha256(code.encode("utf-8")).hexdigest()

    def submit_report(
        self,
        *,
        organization_id: uuid.UUID,
        category: str,
        description: str,
    ) -> tuple[WhistleblowerReport, str]:
        raw_tracking_code = self.generate_tracking_code()
        tracking_code_hash = self.hash_tracking_code(raw_tracking_code)
        anonymous_id = self.generate_anonymous_id()

        report = WhistleblowerReport(
            organization_id=organization_id,
            anonymous_id=anonymous_id,
            tracking_code_hash=tracking_code_hash,
            category=category,
            description=description,
            status="submitted",
        )
        self.db.add(report)
        self.db.flush()

        # CRITICAL: no actor_user_id (there is no real user), no ip_address/user_agent,
        # and after_json contains ONLY the non-identifying anonymous_id + category.
        AuditService(self.db).write_audit_log(
            action="whistleblower_report.submitted",
            entity_type="whistleblower_report",
            entity_id=report.id,
            organization_id=organization_id,
            actor_user_id=None,
            after_json={"anonymous_id": anonymous_id, "category": category},
            ip_address=None,
            user_agent=None,
        )
        return report, raw_tracking_code

    def lookup_report_by_tracking_code(
        self, *, tracking_code: str, organization_id: uuid.UUID | None = None
    ) -> WhistleblowerReport | None:
        # tracking_code_hash is globally unique (see model), so the tracking code
        # alone is sufficient as a credential; organization_id is an optional
        # extra scoping filter for callers that already know the org.
        tracking_code_hash = self.hash_tracking_code(tracking_code)
        stmt = select(WhistleblowerReport).where(WhistleblowerReport.tracking_code_hash == tracking_code_hash)
        if organization_id is not None:
            stmt = stmt.where(WhistleblowerReport.organization_id == organization_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_messages(self, report_id: uuid.UUID) -> list[WhistleblowerMessage]:
        return list(
            self.db.execute(
                select(WhistleblowerMessage)
                .where(WhistleblowerMessage.report_id == report_id)
                .order_by(WhistleblowerMessage.created_at.asc())
            )
            .scalars()
            .all()
        )

    def add_reporter_message(
        self,
        *,
        tracking_code: str,
        content: str,
    ) -> WhistleblowerMessage:
        report = self.lookup_report_by_tracking_code(tracking_code=tracking_code)
        if report is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

        message = WhistleblowerMessage(
            report_id=report.id,
            sender_type="reporter",
            sender_user_id=None,
            content=content,
        )
        self.db.add(message)
        self.db.flush()

        # CRITICAL: reporter messages are never attributable to a real identity.
        AuditService(self.db).write_audit_log(
            action="whistleblower_report.reporter_message_added",
            entity_type="whistleblower_report",
            entity_id=report.id,
            organization_id=report.organization_id,
            actor_user_id=None,
            after_json={"anonymous_id": report.anonymous_id},
            ip_address=None,
            user_agent=None,
        )
        return message

    def add_investigator_message(
        self,
        *,
        organization_id: uuid.UUID,
        report_id: uuid.UUID,
        investigator_user_id: uuid.UUID,
        content: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> WhistleblowerMessage:
        report = self._get_report_for_org(organization_id, report_id)

        message = WhistleblowerMessage(
            report_id=report.id,
            sender_type="investigator",
            sender_user_id=investigator_user_id,
            content=content,
        )
        self.db.add(message)
        self.db.flush()

        # Investigators are staff, not anonymous -- real actor/ip/user_agent are fine here.
        AuditService(self.db).write_audit_log(
            action="whistleblower_report.investigator_message_added",
            entity_type="whistleblower_report",
            entity_id=report.id,
            organization_id=organization_id,
            actor_user_id=investigator_user_id,
            after_json={"message_id": str(message.id)},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return message

    def list_for_investigator(
        self, *, organization_id: uuid.UUID, status_filter: str | None = None
    ) -> list[WhistleblowerReport]:
        stmt = select(WhistleblowerReport).where(WhistleblowerReport.organization_id == organization_id)
        if status_filter is not None:
            stmt = stmt.where(WhistleblowerReport.status == status_filter)
        stmt = stmt.order_by(WhistleblowerReport.created_at.desc())
        return list(self.db.execute(stmt).scalars().all())

    def get_report_for_investigator(self, *, organization_id: uuid.UUID, report_id: uuid.UUID) -> WhistleblowerReport:
        return self._get_report_for_org(organization_id, report_id)

    def update_status(
        self,
        *,
        organization_id: uuid.UUID,
        report_id: uuid.UUID,
        investigator_user_id: uuid.UUID,
        new_status: str,
        resolution_summary: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> WhistleblowerReport:
        report = self._get_report_for_org(organization_id, report_id)

        allowed_next = _VALID_STATUS_TRANSITIONS.get(report.status, set())
        if new_status != report.status and new_status not in allowed_next:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status transition from '{report.status}' to '{new_status}'",
            )

        before = {"status": report.status}
        report.status = new_status
        report.assigned_investigator_user_id = investigator_user_id
        if resolution_summary is not None:
            report.resolution_summary = resolution_summary
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="whistleblower_report.status_updated",
            entity_type="whistleblower_report",
            entity_id=report.id,
            organization_id=organization_id,
            actor_user_id=investigator_user_id,
            before_json=before,
            after_json={"status": new_status},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return report

    def _get_report_for_org(self, organization_id: uuid.UUID, report_id: uuid.UUID) -> WhistleblowerReport:
        report = self.db.execute(
            select(WhistleblowerReport).where(
                WhistleblowerReport.organization_id == organization_id,
                WhistleblowerReport.id == report_id,
            )
        ).scalar_one_or_none()
        if report is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
        return report
