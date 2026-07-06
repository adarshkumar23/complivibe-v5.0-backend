from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.services.audit_engagement_service import AuditEngagementService
from app.compliance.services.auditor_portal_service import AuditorPortalService
from app.models.auditor import Auditor
from app.models.auditor_engagement import AuditorEngagement
from app.models.framework import Framework
from app.models.membership import Membership
from app.schemas.audit_engagement import AuditEngagementCreate
from app.schemas.auditor_marketplace import AuditorEngagementCreate
from app.schemas.auditor_portal import AuditorPortalInvitationCreate
from app.services.audit_service import AuditService

AUDITOR_SEEDS: list[dict] = [
    {
        "name": "Aarav Khanna",
        "email": "aarav.khanna.audit@example.com",
        "firm": "Khanna Assurance LLP",
        "certifications_json": ["ISO 27001 Lead Auditor", "SOC 2 Practitioner"],
        "frameworks_json": ["SOC2", "ISO_27001", "INDIA_DPDP"],
        "rate_usd_per_day": 1200.0,
        "availability": "available",
        "verified": True,
        "bio": "Audit lead with SaaS compliance and cross-border privacy experience.",
    },
    {
        "name": "Maya Iyer",
        "email": "maya.iyer.audit@example.com",
        "firm": "Iyer Cyber Audit Partners",
        "certifications_json": ["CISA", "ISO 27001 Lead Implementer"],
        "frameworks_json": ["ISO_27001", "GDPR", "EU_AI_ACT"],
        "rate_usd_per_day": 1400.0,
        "availability": "limited",
        "verified": True,
        "bio": "Specialist in control design assurance and AI governance readiness reviews.",
    },
]


class AuditorMarketplaceService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)
        self.audit_engagement_service = AuditEngagementService(db)
        self.portal_service = AuditorPortalService(db)

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def ensure_seed_auditors(self) -> None:
        existing = {
            row.email: row
            for row in self.db.execute(select(Auditor).where(Auditor.status != "archived")).scalars().all()
        }
        for payload in AUDITOR_SEEDS:
            row = existing.get(payload["email"])
            if row is None:
                self.db.add(Auditor(**payload, status="active"))
            else:
                for field, value in payload.items():
                    setattr(row, field, value)
                row.status = "active"
        self.db.flush()

    def list_auditors(
        self,
        *,
        framework: str | None = None,
        certification: str | None = None,
        verified: bool | None = None,
        max_rate_usd_per_day: float | None = None,
    ) -> list[Auditor]:
        self.ensure_seed_auditors()
        rows = self.db.execute(
            select(Auditor).where(Auditor.status == "active").order_by(Auditor.verified.desc(), Auditor.rate_usd_per_day.asc())
        ).scalars().all()

        filtered: list[Auditor] = []
        for row in rows:
            if verified is not None and row.verified is not verified:
                continue
            if max_rate_usd_per_day is not None and float(row.rate_usd_per_day) > max_rate_usd_per_day:
                continue
            frameworks = {item.lower() for item in list(row.frameworks_json or [])}
            certs = {item.lower() for item in list(row.certifications_json or [])}
            if framework is not None and framework.lower() not in frameworks:
                continue
            if certification is not None and certification.lower() not in certs:
                continue
            filtered.append(row)
        return filtered

    def _require_framework(self, framework_id: uuid.UUID) -> Framework:
        row = self.db.execute(select(Framework).where(Framework.id == framework_id)).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework not found")
        return row

    def _require_auditor(self, auditor_id: uuid.UUID) -> Auditor:
        row = self.db.execute(
            select(Auditor).where(Auditor.id == auditor_id, Auditor.status == "active")
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auditor not found")
        return row

    def _require_active_membership(self, organization_id: uuid.UUID, user_id: uuid.UUID) -> None:
        row = self.db.execute(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.user_id == user_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Active organization membership required")

    def create_engagement(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        payload: AuditorEngagementCreate,
    ) -> tuple[AuditorEngagement, uuid.UUID, str]:
        self.ensure_seed_auditors()
        self._require_active_membership(organization_id, actor_user_id)
        framework = self._require_framework(payload.framework_id)
        auditor = self._require_auditor(payload.auditor_id)

        if payload.end_date.date() < payload.start_date.date():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="end_date must be on or after start_date")

        audit_engagement = self.audit_engagement_service.create_engagement(
            organization_id,
            AuditEngagementCreate(
                title=payload.title,
                audit_type="external_certification",
                scope_framework_ids=[payload.framework_id],
                assigned_auditor_ids=[],
                start_date=payload.start_date.date(),
                end_date=payload.end_date.date(),
                lead_auditor_name=auditor.name,
                audit_firm=auditor.firm,
                notes=payload.notes,
            ),
            actor_user_id,
        )

        engagement = AuditorEngagement(
            organization_id=organization_id,
            auditor_id=auditor.id,
            audit_engagement_id=audit_engagement.id,
            framework=framework.code,
            status="active",
            started_at=self.utcnow(),
            revenue_share_fee_pct=payload.revenue_share_fee_pct,
            notes=payload.notes,
            created_by=actor_user_id,
        )
        self.db.add(engagement)
        self.db.flush()

        invitation, plaintext_token = self.portal_service.create_invitation(
            organization_id,
            audit_engagement.id,
            AuditorPortalInvitationCreate(
                auditor_email=auditor.email,
                auditor_name=auditor.name,
                scoped_framework_ids=[payload.framework_id],
                scoped_control_ids=None,
                scoped_evidence_ids=None,
                expires_in_days=payload.invite_days_valid,
            ),
            actor_user_id,
        )

        self.audit.write_audit_log(
            action="auditor_marketplace.engagement_created",
            entity_type="auditor_engagement",
            entity_id=engagement.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            after_json={
                "auditor_id": str(engagement.auditor_id),
                "audit_engagement_id": str(engagement.audit_engagement_id),
                "framework": engagement.framework,
                "status": engagement.status,
                "revenue_share_fee_pct": float(engagement.revenue_share_fee_pct),
            },
            metadata_json={"source": "api", "portal_invitation_id": str(invitation.id)},
        )

        return engagement, invitation.id, plaintext_token
