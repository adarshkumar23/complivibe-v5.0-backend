import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.services.audit_engagement_service import AuditEngagementService
from app.models.audit_engagement import AuditEngagement
from app.models.auditor_portal_invitation import AuditorPortalInvitation
from app.models.compliance_report import ComplianceReport
from app.models.control import Control
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.framework import Framework
from app.models.obligation import Obligation
from app.schemas.auditor_portal import AuditorPortalInvitationCreate
from app.services.audit_service import AuditService
from app.services.email_service import EmailService


class AuditorPortalService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.engagement_service = AuditEngagementService(db)

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    @staticmethod
    def mask_email(email: str) -> str:
        local, _, domain = email.partition("@")
        if not local:
            return f"***@{domain}" if domain else "***"
        return f"{local[0]}***@{domain}" if domain else f"{local[0]}***"

    def require_invitation(self, org_id: uuid.UUID, invitation_id: uuid.UUID) -> AuditorPortalInvitation:
        row = self.db.execute(
            select(AuditorPortalInvitation).where(
                AuditorPortalInvitation.organization_id == org_id,
                AuditorPortalInvitation.id == invitation_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auditor portal invitation not found")
        return row

    def _validate_framework_ids(self, framework_ids: list[uuid.UUID]) -> None:
        if not framework_ids:
            return
        rows = self.db.execute(select(Framework.id).where(Framework.id.in_(framework_ids))).all()
        found = {row[0] for row in rows}
        missing = [str(item) for item in framework_ids if item not in found]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown scoped framework ids: {', '.join(missing)}",
            )

    def _validate_control_ids(
        self,
        org_id: uuid.UUID,
        control_ids: list[uuid.UUID] | None,
        framework_ids: list[str] | None = None,
    ) -> None:
        if not control_ids:
            return
        controls = self.db.execute(
            select(Control).where(
                Control.organization_id == org_id,
                Control.id.in_(control_ids),
            )
        ).scalars().all()
        found = {row.id for row in controls}
        missing = [str(item) for item in control_ids if item not in found]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown scoped control ids: {', '.join(missing)}",
            )

        # Defense-in-depth against framework-scope inheritance bugs: even when an admin
        # explicitly enumerates control ids, those controls must still resolve to a
        # framework within the engagement's own scope_framework_ids. Without this, an
        # invitation could be handed direct visibility into controls belonging to
        # frameworks the engagement was never scoped to.
        if framework_ids:
            obligation_ids = [row.obligation_id for row in controls if row.obligation_id is not None]
            framework_by_obligation: dict[uuid.UUID, uuid.UUID] = {}
            if obligation_ids:
                for obligation in self.db.execute(select(Obligation).where(Obligation.id.in_(obligation_ids))).scalars().all():
                    framework_by_obligation[obligation.id] = obligation.framework_id

            out_of_scope = [
                str(row.id)
                for row in controls
                if row.obligation_id is None
                or str(framework_by_obligation.get(row.obligation_id)) not in framework_ids
            ]
            if out_of_scope:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "scoped_control_ids must resolve to a framework within the engagement's "
                        f"scope_framework_ids; out of scope: {', '.join(out_of_scope)}"
                    ),
                )

    def _validate_evidence_ids(self, org_id: uuid.UUID, evidence_ids: list[uuid.UUID] | None) -> None:
        if not evidence_ids:
            return
        found = {
            row[0]
            for row in self.db.execute(
                select(EvidenceItem.id).where(
                    EvidenceItem.organization_id == org_id,
                    EvidenceItem.id.in_(evidence_ids),
                )
            ).all()
        }
        missing = [str(item) for item in evidence_ids if item not in found]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown scoped evidence ids: {', '.join(missing)}",
            )

    def _queue_invitation_email(self, org_id: uuid.UUID, engagement: AuditEngagement, invitation: AuditorPortalInvitation, actor_id: uuid.UUID) -> None:
        try:
            template = EmailService(self.db).resolve_template_for_org(
                organization_id=org_id,
                template_id=None,
                template_key="evidence_requested",
            )
        except HTTPException as exc:
            if exc.status_code == status.HTTP_404_NOT_FOUND:
                return
            raise

        EmailService(self.db).queue_email(
            organization_id=org_id,
            template=template,
            event_type="auditor_portal_invitation",
            recipient_email=invitation.auditor_email,
            recipient_user_id=None,
            priority="normal",
            scheduled_at=None,
            metadata_json={
                "source": "auditor_portal",
                "invitation_id": str(invitation.id),
                "audit_engagement_id": str(invitation.audit_engagement_id),
                "expires_at": invitation.expires_at.isoformat(),
            },
            created_by_user_id=actor_id,
            variables_json={
                "user_name": invitation.auditor_name or invitation.auditor_email.split("@")[0],
                "request_title": engagement.title,
            },
            initial_status="queued",
        )

    def create_invitation(
        self,
        org_id: uuid.UUID,
        engagement_id: uuid.UUID,
        data: AuditorPortalInvitationCreate,
        created_by: uuid.UUID,
    ) -> tuple[AuditorPortalInvitation, str]:
        engagement = self.engagement_service.require_engagement(org_id, engagement_id)

        expires_in_days = max(1, min(data.expires_in_days or 30, 90))
        if data.expires_in_days > 90:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="expires_in_days cannot exceed 90")

        # Framework-based (default) scoping must always be contained within the parent
        # engagement's own scope_framework_ids -- otherwise an invitation could grant an
        # auditor visibility into frameworks the engagement was never scoped to. When no
        # explicit scoped_framework_ids are supplied, the invitation inherits the
        # engagement's scope rather than defaulting to an empty/unbounded list.
        engagement_framework_ids = list(engagement.scope_framework_ids or [])
        requested_framework_ids = [str(item) for item in data.scoped_framework_ids]
        if requested_framework_ids:
            out_of_scope = [fid for fid in requested_framework_ids if fid not in engagement_framework_ids]
            if out_of_scope:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "scoped_framework_ids must be a subset of the engagement's own "
                        f"scope_framework_ids; not part of engagement scope: {', '.join(out_of_scope)}"
                    ),
                )
            resolved_framework_ids = requested_framework_ids
        else:
            resolved_framework_ids = engagement_framework_ids

        self._validate_framework_ids([uuid.UUID(item) for item in resolved_framework_ids])
        self._validate_control_ids(org_id, data.scoped_control_ids, framework_ids=resolved_framework_ids)
        self._validate_evidence_ids(org_id, data.scoped_evidence_ids)

        plaintext_token = secrets.token_urlsafe(32)
        token_hash = self.hash_token(plaintext_token)

        row = AuditorPortalInvitation(
            organization_id=org_id,
            audit_engagement_id=engagement_id,
            auditor_email=str(data.auditor_email),
            auditor_name=data.auditor_name,
            token_hash=token_hash,
            scoped_framework_ids=resolved_framework_ids,
            scoped_control_ids=[str(item) for item in data.scoped_control_ids] if data.scoped_control_ids is not None else None,
            scoped_evidence_ids=[str(item) for item in data.scoped_evidence_ids] if data.scoped_evidence_ids is not None else None,
            expires_at=self.utcnow() + timedelta(days=expires_in_days),
            first_accessed_at=None,
            last_accessed_at=None,
            access_count=0,
            status="active",
            revoked_at=None,
            revoked_by=None,
            created_by=created_by,
        )
        self.db.add(row)
        self.db.flush()

        self._queue_invitation_email(org_id, engagement, row, created_by)

        AuditService(self.db).write_audit_log(
            action="auditor_portal.invitation_created",
            entity_type="auditor_portal_invitation",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={
                "audit_engagement_id": str(row.audit_engagement_id),
                "auditor_email": row.auditor_email,
                "expires_at": row.expires_at.isoformat(),
                "status": row.status,
            },
            metadata_json={"source": "api"},
        )

        return row, plaintext_token

    def authenticate_portal_token(self, raw_token: str) -> AuditorPortalInvitation:
        token_hash = self.hash_token(raw_token)
        row = self.db.execute(
            select(AuditorPortalInvitation).where(AuditorPortalInvitation.token_hash == token_hash)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid portal token")

        now = self.utcnow()

        if row.status == "revoked":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Portal token revoked")

        expires_at = row.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)

        if expires_at <= now:
            if row.status != "expired":
                row.status = "expired"
                self.db.flush()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Portal token expired")

        if row.status != "active":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid portal token")

        row.access_count = int(row.access_count or 0) + 1
        row.last_accessed_at = now
        if row.first_accessed_at is None:
            row.first_accessed_at = now

        AuditService(self.db).write_audit_log(
            action="auditor_portal.access",
            entity_type="auditor_portal_invitation",
            entity_id=row.id,
            organization_id=row.organization_id,
            actor_user_id=None,
            after_json={
                "status": row.status,
                "access_count": row.access_count,
                "last_accessed_at": row.last_accessed_at.isoformat() if row.last_accessed_at else None,
            },
            metadata_json={"source": "portal"},
        )
        self.db.flush()
        return row

    def revoke_invitation(self, org_id: uuid.UUID, invitation_id: uuid.UUID, revoked_by: uuid.UUID) -> None:
        row = self.require_invitation(org_id, invitation_id)
        before = {"status": row.status, "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None}

        row.status = "revoked"
        row.revoked_at = self.utcnow()
        row.revoked_by = revoked_by
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="auditor_portal.invitation_revoked",
            entity_type="auditor_portal_invitation",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=revoked_by,
            before_json=before,
            after_json={
                "status": row.status,
                "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
                "revoked_by": str(row.revoked_by) if row.revoked_by else None,
            },
            metadata_json={"source": "api"},
        )

    def list_invitations(self, org_id: uuid.UUID, engagement_id: uuid.UUID | None = None) -> list[AuditorPortalInvitation]:
        stmt = select(AuditorPortalInvitation).where(AuditorPortalInvitation.organization_id == org_id)
        if engagement_id is not None:
            stmt = stmt.where(AuditorPortalInvitation.audit_engagement_id == engagement_id)
        return self.db.execute(stmt.order_by(AuditorPortalInvitation.created_at.desc())).scalars().all()

    def get_invitation(self, org_id: uuid.UUID, invitation_id: uuid.UUID) -> AuditorPortalInvitation:
        return self.require_invitation(org_id, invitation_id)

    def log_scoped_data_view(
        self,
        invitation: AuditorPortalInvitation,
        resource_type: str,
        item_ids: list[uuid.UUID],
    ) -> None:
        # Distinct from the login-level "auditor_portal.access" log written on every
        # token authentication: this records which specific scoped resource the
        # auditor actually viewed (and which items), so the audit trail can answer
        # "what did the auditor see", not just "did the auditor log in".
        AuditService(self.db).write_audit_log(
            action="auditor_portal.data_viewed",
            entity_type="auditor_portal_invitation",
            entity_id=invitation.id,
            organization_id=invitation.organization_id,
            actor_user_id=None,
            after_json={
                "resource_type": resource_type,
                "item_count": len(item_ids),
                "item_ids": [str(item) for item in item_ids],
            },
            metadata_json={"source": "portal", "auditor_email": invitation.auditor_email},
        )
        self.db.flush()

    def effective_framework_ids(self, invitation: AuditorPortalInvitation) -> list[uuid.UUID]:
        """Intersect the invitation's snapshotted framework scope with the engagement's
        *current* scope_framework_ids. If the engagement's scope is narrowed (or the
        engagement is soft-deleted) after an invitation was issued, the invitation must
        immediately lose visibility into anything no longer in the live engagement scope
        -- it should never rely solely on the value captured at invitation-creation time.
        """
        engagement = self.db.execute(
            select(AuditEngagement).where(
                AuditEngagement.organization_id == invitation.organization_id,
                AuditEngagement.id == invitation.audit_engagement_id,
                AuditEngagement.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if engagement is None:
            return []

        live_scope = set(engagement.scope_framework_ids or [])
        invitation_scope = set(invitation.scoped_framework_ids or [])
        effective = invitation_scope & live_scope
        return [uuid.UUID(item) for item in effective]

    def get_scoped_controls(self, invitation: AuditorPortalInvitation) -> list[Control]:
        scoped_control_ids = invitation.scoped_control_ids
        stmt = select(Control).where(
            Control.organization_id == invitation.organization_id,
            Control.status != "archived",
        )

        if scoped_control_ids is None:
            framework_ids = self.effective_framework_ids(invitation)
            if not framework_ids:
                return []
            # Control.obligation_id is a legacy FK that no API path ever writes to;
            # the real control<->obligation relationship is tracked via
            # ControlObligationMapping (populated by POST /controls/{id}/obligations).
            stmt = (
                stmt.join(ControlObligationMapping, ControlObligationMapping.control_id == Control.id)
                .join(Obligation, Obligation.id == ControlObligationMapping.obligation_id)
                .where(
                    ControlObligationMapping.organization_id == invitation.organization_id,
                    ControlObligationMapping.status == "active",
                    Obligation.framework_id.in_(framework_ids),
                )
                .distinct()
            )
        else:
            control_ids = [uuid.UUID(item) for item in scoped_control_ids]
            if not control_ids:
                return []
            stmt = stmt.where(Control.id.in_(control_ids))

        return self.db.execute(stmt.order_by(Control.created_at.desc())).scalars().all()

    def get_scoped_evidence(self, invitation: AuditorPortalInvitation) -> list[EvidenceItem]:
        if invitation.scoped_evidence_ids is not None:
            evidence_ids = [uuid.UUID(item) for item in invitation.scoped_evidence_ids]
            if not evidence_ids:
                return []
            return self.db.execute(
                select(EvidenceItem).where(
                    EvidenceItem.organization_id == invitation.organization_id,
                    EvidenceItem.id.in_(evidence_ids),
                    EvidenceItem.status != "archived",
                )
            ).scalars().all()

        controls = self.get_scoped_controls(invitation)
        control_ids = [row.id for row in controls]
        if not control_ids:
            return []

        return self.db.execute(
            select(EvidenceItem)
            .join(EvidenceControlLink, EvidenceControlLink.evidence_item_id == EvidenceItem.id)
            .where(
                EvidenceItem.organization_id == invitation.organization_id,
                EvidenceItem.status != "archived",
                EvidenceControlLink.organization_id == invitation.organization_id,
                EvidenceControlLink.control_id.in_(control_ids),
                EvidenceControlLink.link_status == "active",
            )
            .distinct()
            .order_by(EvidenceItem.created_at.desc())
        ).scalars().all()

    def get_scoped_reports(self, invitation: AuditorPortalInvitation) -> list[ComplianceReport]:
        framework_ids = self.effective_framework_ids(invitation)
        if not framework_ids:
            return []

        return self.db.execute(
            select(ComplianceReport).where(
                ComplianceReport.organization_id == invitation.organization_id,
                ComplianceReport.framework_id.in_(framework_ids),
            )
            .order_by(ComplianceReport.generated_at.desc())
        ).scalars().all()
