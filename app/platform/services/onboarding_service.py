from __future__ import annotations

import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, get_password_hash
from app.models.control import Control
from app.models.evidence_item import EvidenceItem
from app.models.email_outbox import EmailOutbox
from app.models.framework import Framework
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.organization_framework import OrganizationFramework
from app.models.risk import Risk
from app.models.role import Role
from app.models.team_invitation import TeamInvitation
from app.models.user import User
from app.platform.services.billing_service import BillingService
from app.platform.services.competitor_pricing_service import CompetitorPricingService
from app.services.audit_service import AuditService
from app.services.seed_service import SeedService


class OnboardingService:
    ROLE_CODE_FALLBACKS: dict[str, list[str]] = {
        "member": ["viewer", "compliance_manager", "admin", "owner"],
    }

    @staticmethod
    def _slugify(value: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        return base[:80] or "organization"

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def select_plan_options(self, db: Session) -> dict:
        plans = BillingService(db).list_plans()
        pricing_snapshot = CompetitorPricingService(db).latest_snapshot_payload()
        return {
            "available_plans": [
                {
                    "plan_code": item.plan_code,
                    "display_name": item.display_name,
                    "price_inr_monthly": item.price_inr_monthly,
                    "price_inr_annual": item.price_inr_annual,
                    "features": item.features or {},
                }
                for item in plans
            ],
            "competitor_pricing": pricing_snapshot,
        }

    def start_onboarding(
        self,
        org_name: str,
        org_slug: str,
        admin_email: str,
        admin_full_name: str,
        admin_password: str,
        db: Session,
    ) -> dict:
        normalized_slug = self._slugify(org_slug)
        existing = db.execute(select(Organization).where(Organization.slug == normalized_slug)).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Organization slug '{normalized_slug}' is already taken",
            )

        normalized_email = admin_email.strip().lower()
        existing_user = db.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists. Please log in instead.",
            )

        user = User(
            email=normalized_email,
            full_name=admin_full_name,
            hashed_password=get_password_hash(admin_password),
            status="active",
            is_active=True,
            is_superuser=False,
        )
        db.add(user)
        db.flush()

        org = Organization(
            name=org_name,
            slug=normalized_slug,
            is_active=True,
            onboarding_step="org_created",
            created_by=user.id,
        )
        db.add(org)
        db.flush()

        roles = SeedService.ensure_roles_for_organization(db, org.id)
        SeedService.ensure_policy_templates(db)
        SeedService.ensure_questionnaire_scoring_rules(db)
        SeedService.ensure_issue_sla_policies(db, org.id)
        SeedService.ensure_default_data_access_anomaly_rules(db, org.id, user.id)

        owner_role = roles.get("owner")
        owner_role_id = owner_role.id if hasattr(owner_role, "id") else owner_role
        membership = Membership(
            organization_id=org.id,
            user_id=user.id,
            role_id=owner_role_id,
            status="active",
            invited_by=user.id,
        )
        db.add(membership)
        db.flush()

        BillingService(db).start_trial(org_id=org.id)
        self._queue_welcome_email(org=org, user=user, db=db)

        AuditService(db).write_audit_log(
            action="onboarding.org_created",
            entity_type="organizations",
            organization_id=org.id,
            actor_user_id=user.id,
            entity_id=org.id,
            metadata_json={"source": "onboarding.start"},
        )

        token = create_access_token(subject=user.id)

        return {
            "org_id": str(org.id),
            "org_slug": org.slug,
            "user_id": str(user.id),
            "access_token": token,
            "token_type": "bearer",
            "onboarding_step": org.onboarding_step or "org_created",
        }

    def select_frameworks(
        self,
        org_id: uuid.UUID,
        framework_ids: list[uuid.UUID],
        user_id: uuid.UUID,
        db: Session,
    ) -> dict:
        org = db.get(Organization, org_id)
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Org not found")

        activated: list[str] = []
        skipped: list[str] = []
        now = self.utcnow()

        for fw_id in framework_ids:
            framework = db.execute(
                select(Framework).where(
                    Framework.id == fw_id,
                    Framework.status == "active",
                )
            ).scalar_one_or_none()
            if framework is None:
                skipped.append(str(fw_id))
                continue

            org_framework = db.execute(
                select(OrganizationFramework).where(
                    OrganizationFramework.organization_id == org_id,
                    OrganizationFramework.framework_id == fw_id,
                )
            ).scalar_one_or_none()

            if org_framework is None:
                org_framework = OrganizationFramework(
                    organization_id=org_id,
                    framework_id=fw_id,
                    status="active",
                    activated_by_user_id=user_id,
                    activated_at=now,
                )
                db.add(org_framework)
            elif org_framework.status != "active":
                org_framework.status = "active"
                org_framework.activated_by_user_id = user_id
                org_framework.activated_at = now
                org_framework.deactivated_by_user_id = None
                org_framework.deactivated_at = None

            activated.append(framework.name)

        org.onboarding_step = "frameworks_selected"
        db.flush()

        AuditService(db).write_audit_log(
            action="onboarding.frameworks_selected",
            entity_type="organizations",
            organization_id=org_id,
            actor_user_id=user_id,
            entity_id=org_id,
            metadata_json={"frameworks": activated},
        )

        return {
            "activated": activated,
            "skipped": skipped,
            "onboarding_step": org.onboarding_step,
        }

    def invite_team_members(
        self,
        org_id: uuid.UUID,
        invites: list[dict],
        invited_by: uuid.UUID,
        db: Session,
    ) -> dict:
        org = db.get(Organization, org_id)
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Org not found")

        invited: list[str] = []
        skipped: list[dict[str, str]] = []

        for invite in invites:
            email = str(invite.get("email", "")).strip().lower()
            role_code = str(invite.get("role_code", "member")).strip().lower() or "member"
            if not email:
                continue

            existing_user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
            if existing_user is not None:
                existing_membership = db.execute(
                    select(Membership).where(
                        Membership.organization_id == org_id,
                        Membership.user_id == existing_user.id,
                    )
                ).scalar_one_or_none()
                if existing_membership is not None:
                    skipped.append({"email": email, "reason": "already_member"})
                    continue

            existing_invite = db.execute(
                select(TeamInvitation).where(
                    TeamInvitation.organization_id == org_id,
                    TeamInvitation.email == email,
                    TeamInvitation.status == "pending",
                )
            ).scalar_one_or_none()
            if existing_invite is not None:
                skipped.append({"email": email, "reason": "already_invited"})
                continue

            invitation = TeamInvitation(
                organization_id=org_id,
                email=email,
                role_code=role_code,
                invited_by=invited_by,
                token=secrets.token_urlsafe(48),
                status="pending",
                expires_at=self.utcnow() + timedelta(days=7),
                created_at=self.utcnow(),
            )
            db.add(invitation)
            db.flush()

            self._queue_invitation_email(org=org, invitation=invitation, db=db)
            invited.append(email)

        org.onboarding_step = "team_invited"
        db.flush()

        AuditService(db).write_audit_log(
            action="onboarding.team_invited",
            entity_type="organizations",
            organization_id=org_id,
            actor_user_id=invited_by,
            entity_id=org_id,
            metadata_json={"invited_count": len(invited)},
        )

        return {
            "invited": invited,
            "skipped": skipped,
            "onboarding_step": org.onboarding_step,
        }

    def accept_invitation(
        self,
        token: str,
        full_name: str,
        password: str,
        db: Session,
    ) -> dict:
        invitation = db.execute(
            select(TeamInvitation).where(
                TeamInvitation.token == token,
                TeamInvitation.status == "pending",
            )
        ).scalar_one_or_none()

        if invitation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invitation not found or already used",
            )

        if self._as_utc(invitation.expires_at) < self.utcnow():
            invitation.status = "expired"
            db.flush()
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="This invitation has expired. Please request a new one.",
            )

        role = db.execute(
            select(Role).where(
                Role.organization_id == invitation.organization_id,
                Role.name == invitation.role_code,
            )
        ).scalar_one_or_none()
        if role is None:
            for candidate in self.ROLE_CODE_FALLBACKS.get(invitation.role_code, []):
                role = db.execute(
                    select(Role).where(
                        Role.organization_id == invitation.organization_id,
                        Role.name == candidate,
                    )
                ).scalar_one_or_none()
                if role is not None:
                    break
        if role is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role not found for invitation")

        user = db.execute(select(User).where(User.email == invitation.email)).scalar_one_or_none()
        if user is None:
            user = User(
                email=invitation.email,
                full_name=full_name,
                hashed_password=get_password_hash(password),
                is_active=True,
                status="active",
                is_superuser=False,
            )
            db.add(user)
            db.flush()
        else:
            user.full_name = full_name
            user.hashed_password = get_password_hash(password)
            user.is_active = True
            user.status = "active"

        existing_membership = db.execute(
            select(Membership).where(
                Membership.organization_id == invitation.organization_id,
                Membership.user_id == user.id,
            )
        ).scalar_one_or_none()
        if existing_membership is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already a member")

        membership = Membership(
            organization_id=invitation.organization_id,
            user_id=user.id,
            role_id=role.id if role else None,
            status="active",
            invited_by=invitation.invited_by,
        )
        db.add(membership)

        invitation.status = "accepted"
        invitation.accepted_at = self.utcnow()
        db.flush()

        AuditService(db).write_audit_log(
            action="onboarding.invitation_accepted",
            entity_type="memberships",
            organization_id=invitation.organization_id,
            actor_user_id=user.id,
            entity_id=membership.id,
        )

        token_str = create_access_token(subject=user.id)
        return {
            "user_id": str(user.id),
            "org_id": str(invitation.organization_id),
            "access_token": token_str,
            "token_type": "bearer",
        }

    def list_team_invitations(self, org_id: uuid.UUID, db: Session) -> list[TeamInvitation]:
        return db.execute(
            select(TeamInvitation)
            .where(TeamInvitation.organization_id == org_id)
            .order_by(TeamInvitation.created_at.desc())
        ).scalars().all()

    def revoke_invitation(self, org_id: uuid.UUID, invitation_id: uuid.UUID, user_id: uuid.UUID, db: Session) -> TeamInvitation:
        invitation = db.execute(
            select(TeamInvitation).where(
                TeamInvitation.id == invitation_id,
                TeamInvitation.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if invitation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
        if invitation.status != "pending":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending invitations can be revoked")

        invitation.status = "revoked"
        db.flush()

        AuditService(db).write_audit_log(
            action="onboarding.invitation_revoked",
            entity_type="team_invitations",
            organization_id=org_id,
            actor_user_id=user_id,
            entity_id=invitation.id,
        )
        return invitation

    def get_checklist(self, org_id: uuid.UUID, db: Session) -> dict:
        org = db.get(Organization, org_id)
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Org not found")

        first_active_framework = db.execute(
            select(OrganizationFramework)
            .where(
                OrganizationFramework.organization_id == org_id,
                OrganizationFramework.status == "active",
            )
            .order_by(OrganizationFramework.activated_at.asc())
            .limit(1)
        ).scalar_one_or_none()
        has_frameworks = first_active_framework is not None

        has_team = (
            db.execute(
                select(Membership)
                .where(Membership.organization_id == org_id)
                .order_by(Membership.created_at.asc())
            ).scalars().all()
        )
        has_multiple_members = len(has_team) > 1
        first_pending_invite = db.execute(
            select(TeamInvitation)
            .where(
                TeamInvitation.organization_id == org_id,
                TeamInvitation.status == "pending",
            )
            .order_by(TeamInvitation.created_at.asc())
            .limit(1)
        ).scalar_one_or_none()
        has_pending_invites = first_pending_invite is not None

        first_control = db.execute(
            select(Control).where(Control.organization_id == org_id).order_by(Control.created_at.asc()).limit(1)
        ).scalar_one_or_none()
        has_controls = first_control is not None

        first_risk = db.execute(
            select(Risk).where(Risk.organization_id == org_id).order_by(Risk.created_at.asc()).limit(1)
        ).scalar_one_or_none()
        has_risks = first_risk is not None

        first_verified_evidence = db.execute(
            select(EvidenceItem)
            .where(
                EvidenceItem.organization_id == org_id,
                EvidenceItem.review_status == "verified",
            )
            .order_by(EvidenceItem.created_at.asc())
            .limit(1)
        ).scalar_one_or_none()
        has_verified_evidence = first_verified_evidence is not None

        checks = {
            "org_created": True,
            "frameworks_selected": has_frameworks,
            "team_invited_or_has_members": has_multiple_members or has_pending_invites,
            "has_controls": has_controls,
            "has_risks": has_risks,
            "evidence_uploaded": has_verified_evidence,
        }

        core_check_keys = (
            "org_created",
            "frameworks_selected",
            "team_invited_or_has_members",
            "has_controls",
            "has_risks",
        )
        completed_count = sum(1 for key in core_check_keys if checks[key])
        completion_percentage = round((completed_count / len(core_check_keys)) * 100)

        evidence_completed_at = None
        if first_verified_evidence is not None:
            evidence_completed_at = (
                first_verified_evidence.reviewed_at
                or first_verified_evidence.collected_at
                or first_verified_evidence.created_at
            )

        frameworks_completed_at = first_active_framework.activated_at if first_active_framework else None

        team_completed_at = None
        if has_multiple_members:
            # has_team is ordered by created_at ascending; index 0 is the org creator, so the
            # second entry is the first genuinely "invited" additional member.
            team_completed_at = has_team[1].created_at
        elif has_pending_invites:
            team_completed_at = first_pending_invite.created_at

        controls_completed_at = first_control.created_at if first_control else None
        risks_completed_at = first_risk.created_at if first_risk else None

        checklist_items = [
            {"id": "org_created", "label": "Create your organization", "completed": True, "completed_at": org.created_at},
            {
                "id": "frameworks_selected",
                "label": "Select at least one framework",
                "completed": has_frameworks,
                "completed_at": frameworks_completed_at,
            },
            {
                "id": "team_invited_or_has_members",
                "label": "Invite your team",
                "completed": has_multiple_members or has_pending_invites,
                "completed_at": team_completed_at,
            },
            {
                "id": "has_controls",
                "label": "Add your first control",
                "completed": has_controls,
                "completed_at": controls_completed_at,
            },
            {
                "id": "has_risks",
                "label": "Add your first risk",
                "completed": has_risks,
                "completed_at": risks_completed_at,
            },
            {
                "id": "evidence_uploaded",
                "label": "Upload your first piece of evidence",
                "completed": has_verified_evidence,
                "completed_at": evidence_completed_at,
            },
        ]

        return {
            "org_id": str(org_id),
            "onboarding_step": org.onboarding_step or "not_started",
            "onboarding_completed": bool(org.onboarding_completed),
            "checklist": checks,
            "checklist_items": checklist_items,
            "completion_percentage": completion_percentage,
        }

    def complete_onboarding(self, org_id: uuid.UUID, user_id: uuid.UUID, db: Session) -> dict:
        org = db.get(Organization, org_id)
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Org not found")

        org.onboarding_completed = True
        org.onboarding_completed_at = self.utcnow()
        org.onboarding_step = "completed"
        db.flush()

        AuditService(db).write_audit_log(
            action="onboarding.completed",
            entity_type="organizations",
            organization_id=org_id,
            actor_user_id=user_id,
            entity_id=org_id,
        )

        return {
            "org_id": str(org_id),
            "onboarding_completed": True,
            "completed_at": org.onboarding_completed_at.isoformat() if org.onboarding_completed_at else None,
        }

    def _queue_welcome_email(self, org: Organization, user: User, db: Session) -> None:
        now = self.utcnow()
        subject = f"Welcome to CompliVibe, {user.full_name or user.email}"
        body_text = (
            f"Welcome to CompliVibe, {user.full_name or user.email}.\n"
            f"Your organization '{org.name}' is ready.\n"
            "Next steps: choose frameworks, invite your team, and complete onboarding."
        )
        body_html = (
            f"<p>Welcome to CompliVibe, <strong>{user.full_name or user.email}</strong>.</p>"
            f"<p>Your organization <strong>{org.name}</strong> is ready.</p>"
            "<p>Next steps: choose frameworks, invite your team, and complete onboarding.</p>"
        )

        db.add(
            EmailOutbox(
                organization_id=org.id,
                template_id=None,
                event_type="onboarding.welcome",
                template_name="onboarding_welcome",
                template_context={"org_name": org.name, "user_name": user.full_name or user.email},
                recipient_email=user.email,
                recipient_user_id=user.id,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                status="pending",
                priority="normal",
                queued_at=now,
                attempt_count=0,
                max_attempts=3,
                metadata_json={"source": "onboarding.start"},
                created_by_user_id=user.id,
            )
        )

    def _queue_invitation_email(self, org: Organization, invitation: TeamInvitation, db: Session) -> None:
        now = self.utcnow()
        frontend_url = get_settings().FRONTEND_URL
        accept_link = f"{frontend_url}/accept-invite?token={invitation.token}"

        subject = f"You're invited to join {org.name} on CompliVibe"
        body_text = (
            f"You were invited to join {org.name}.\n"
            f"Accept your invitation: {accept_link}\n"
            "This link expires in 7 days."
        )
        body_html = (
            f"<p>You were invited to join <strong>{org.name}</strong>.</p>"
            f"<p><a href=\"{accept_link}\">Accept your invitation</a></p>"
            "<p>This link expires in 7 days.</p>"
        )

        db.add(
            EmailOutbox(
                organization_id=org.id,
                template_id=None,
                event_type="onboarding.team_invite",
                template_name="onboarding_team_invite",
                template_context={
                    "org_name": org.name,
                    "invite_email": invitation.email,
                    "accept_link": accept_link,
                },
                recipient_email=invitation.email,
                recipient_user_id=None,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                status="pending",
                priority="normal",
                queued_at=now,
                attempt_count=0,
                max_attempts=3,
                metadata_json={"invitation_id": str(invitation.id)},
                created_by_user_id=invitation.invited_by,
            )
        )
