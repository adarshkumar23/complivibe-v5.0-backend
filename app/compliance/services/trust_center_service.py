import hashlib
import re
import secrets
import uuid
from datetime import UTC, timedelta, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.compliance_certification import ComplianceCertification
from app.models.compliance_policy import CompliancePolicy
from app.models.email_outbox import EmailOutbox
from app.models.framework import Framework
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.organization_framework import OrganizationFramework
from app.models.role import Role
from app.models.trust_center_access_request import TrustCenterAccessRequest
from app.models.trust_center_configuration import TrustCenterConfiguration
from app.models.trust_center_published_policy import TrustCenterPublishedPolicy
from app.models.user import User
from app.platform.services.competitor_pricing_service import CompetitorPricingService
from app.services.audit_service import AuditService
from app.services.compliance_dashboard_service import ComplianceDashboardService

SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,98}[a-z0-9]$")


class TrustCenterService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    def get_org_by_slug(self, slug: str) -> Organization | None:
        return self.db.execute(select(Organization).where(Organization.slug == slug)).scalar_one_or_none()

    def _require_org(self, org_id: uuid.UUID) -> Organization:
        row = self.db.execute(select(Organization).where(Organization.id == org_id)).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
        return row

    def _require_config(self, org_id: uuid.UUID) -> TrustCenterConfiguration:
        row = self.db.execute(
            select(TrustCenterConfiguration).where(TrustCenterConfiguration.organization_id == org_id)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trust center configuration not found")
        return row

    def _require_access_request(self, org_id: uuid.UUID, request_id: uuid.UUID) -> TrustCenterAccessRequest:
        row = self.db.execute(
            select(TrustCenterAccessRequest).where(
                TrustCenterAccessRequest.organization_id == org_id,
                TrustCenterAccessRequest.id == request_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access request not found")
        return row

    def get_trust_center_public_data(self, slug: str) -> dict:
        org = self.get_org_by_slug(slug)
        if org is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trust center not found")

        config = self.db.execute(
            select(TrustCenterConfiguration).where(TrustCenterConfiguration.organization_id == org.id)
        ).scalar_one_or_none()
        if config is None or not config.is_enabled:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trust center not found")

        certifications: list[dict] = []
        expired_certifications_excluded = 0
        if config.show_certifications:
            cert_rows = self.db.execute(
                select(ComplianceCertification).where(
                    ComplianceCertification.organization_id == org.id,
                    ComplianceCertification.status == "active",
                    ComplianceCertification.deleted_at.is_(None),
                )
            ).scalars().all()
            today = self.utcnow().date()
            for row in cert_rows:
                if row.valid_until is not None and row.valid_until < today:
                    # A certification marked "active" in the source system but past its
                    # valid_until date is stale data — do not surface it publicly as a
                    # currently-valid credential.
                    expired_certifications_excluded += 1
                    continue
                certifications.append(
                    {
                        "name": row.name,
                        "issued_by": row.issuer,
                        "valid_until": row.valid_until,
                    }
                )

        framework_coverage: list[dict] = []
        if config.show_framework_coverage:
            framework_rows = self.db.execute(
                select(Framework)
                .join(OrganizationFramework, OrganizationFramework.framework_id == Framework.id)
                .where(
                    OrganizationFramework.organization_id == org.id,
                    OrganizationFramework.status == "active",
                )
                .order_by(Framework.name.asc())
            ).scalars().all()

            dashboard_service = ComplianceDashboardService(self.db)
            for framework in framework_rows:
                # Reuse the same real control-coverage calculation as the (working)
                # admin-side posture-summary/framework-readiness endpoints, which map
                # controls to obligations via ControlObligationMapping. The previous
                # query here joined on the legacy, unpopulated Control.obligation_id
                # column and therefore always returned 0% regardless of real coverage.
                coverage_pct = int(round(dashboard_service.framework_control_coverage_pct(org.id, framework.id)))
                framework_coverage.append({"framework_name": framework.name, "coverage_pct": coverage_pct})

        policies: list[dict] = []
        if config.show_published_policies:
            rows = self.db.execute(
                select(TrustCenterPublishedPolicy, CompliancePolicy)
                .join(CompliancePolicy, CompliancePolicy.id == TrustCenterPublishedPolicy.policy_id)
                .where(
                    TrustCenterPublishedPolicy.organization_id == org.id,
                    TrustCenterPublishedPolicy.is_active.is_(True),
                    CompliancePolicy.organization_id == org.id,
                    CompliancePolicy.archived_at.is_(None),
                )
                .order_by(TrustCenterPublishedPolicy.published_at.desc())
            ).all()
            policies = [{"title": policy.title, "summary": published.summary} for published, policy in rows]

        uptime = None
        if config.show_uptime_status and config.uptime_status is not None:
            uptime = {
                "status": config.uptime_status,
                "updated_at": config.uptime_updated_at,
            }

        pricing_snapshot = CompetitorPricingService(self.db).latest_snapshot_payload()
        competitor_pricing = [
            {
                "competitor_name": row["competitor_name"],
                "pricing_model": row["pricing_model"],
                "pricing_summary": row["pricing_summary"],
                "source_url": row["source_url"],
                "last_verified_at": row["last_verified_at"],
            }
            for row in pricing_snapshot["entries"]
        ]

        return {
            "organization_slug": slug,
            "display_name": config.display_name or org.name,
            "tagline": config.tagline,
            "logo_url": config.logo_url,
            "contact_email": config.contact_email,
            "custom_message": config.custom_message,
            "certifications": certifications,
            "framework_coverage": framework_coverage,
            "policies": policies,
            "competitor_pricing": competitor_pricing,
            "competitor_pricing_last_updated": pricing_snapshot["last_updated"],
            "uptime": uptime,
            "data_generated_at": self.utcnow(),
            "expired_certifications_excluded": expired_certifications_excluded,
        }

    def get_configuration(self, org_id: uuid.UUID) -> TrustCenterConfiguration:
        return self._require_config(org_id)

    def create_or_update_configuration(self, org_id: uuid.UUID, data, user_id: uuid.UUID) -> TrustCenterConfiguration:
        self._require_org(org_id)
        row = self.db.execute(
            select(TrustCenterConfiguration).where(TrustCenterConfiguration.organization_id == org_id)
        ).scalar_one_or_none()

        before = None
        if row is None:
            row = TrustCenterConfiguration(organization_id=org_id)
            self.db.add(row)
        else:
            before = {
                "is_enabled": row.is_enabled,
                "display_name": row.display_name,
                "show_published_policies": row.show_published_policies,
            }

        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(row, key, value)

        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="trust_center.configured",
            entity_type="trust_center_configuration",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            before_json=before,
            after_json={
                "is_enabled": row.is_enabled,
                "display_name": row.display_name,
                "show_published_policies": row.show_published_policies,
            },
            metadata_json={"source": "api"},
        )
        return row

    def set_org_slug(self, org_id: uuid.UUID, slug: str, user_id: uuid.UUID) -> Organization:
        if not SLUG_PATTERN.fullmatch(slug):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Slug must be lowercase alphanumeric and hyphens, 3-100 chars",
            )

        org = self._require_org(org_id)
        existing = self.db.execute(
            select(Organization).where(
                Organization.slug == slug,
                Organization.id != org_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Slug already in use")

        before = {"slug": org.slug}
        org.slug = slug
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="trust_center.slug_set",
            entity_type="organization",
            entity_id=org.id,
            organization_id=org_id,
            actor_user_id=user_id,
            before_json=before,
            after_json={"slug": org.slug},
            metadata_json={"source": "api"},
        )
        return org

    def publish_policy(self, org_id: uuid.UUID, policy_id: uuid.UUID, summary: str | None, user_id: uuid.UUID) -> TrustCenterPublishedPolicy:
        policy = self.db.execute(
            select(CompliancePolicy).where(
                CompliancePolicy.id == policy_id,
                CompliancePolicy.organization_id == org_id,
                CompliancePolicy.archived_at.is_(None),
                CompliancePolicy.status != "archived",
            )
        ).scalar_one_or_none()
        if policy is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")

        if policy.status != "approved":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Cannot publish policy to the trust center while it is in '{policy.status}' status. "
                    "Only approved policies may be published publicly."
                ),
            )

        row = self.db.execute(
            select(TrustCenterPublishedPolicy).where(
                TrustCenterPublishedPolicy.organization_id == org_id,
                TrustCenterPublishedPolicy.policy_id == policy_id,
            )
        ).scalar_one_or_none()
        if row is None:
            row = TrustCenterPublishedPolicy(
                organization_id=org_id,
                policy_id=policy_id,
                summary=summary,
                published_by=user_id,
                is_active=True,
            )
            self.db.add(row)
        else:
            row.summary = summary
            row.published_by = user_id
            row.published_at = self.utcnow()
            row.is_active = True

        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="trust_center.policy_published",
            entity_type="trust_center_published_policy",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"policy_id": str(policy_id), "is_active": row.is_active},
            metadata_json={"source": "api"},
        )
        return row

    def list_published_policies(self, org_id: uuid.UUID, include_inactive: bool = False) -> list[dict]:
        stmt = (
            select(TrustCenterPublishedPolicy, CompliancePolicy)
            .join(CompliancePolicy, CompliancePolicy.id == TrustCenterPublishedPolicy.policy_id)
            .where(TrustCenterPublishedPolicy.organization_id == org_id)
        )
        if not include_inactive:
            stmt = stmt.where(TrustCenterPublishedPolicy.is_active.is_(True))
        rows = self.db.execute(stmt.order_by(TrustCenterPublishedPolicy.published_at.desc())).all()

        results: list[dict] = []
        for published, policy in rows:
            policy_updated_since_published = policy.updated_at > published.published_at
            results.append(
                {
                    "id": published.id,
                    "organization_id": published.organization_id,
                    "policy_id": published.policy_id,
                    "policy_title": policy.title,
                    "policy_archived": policy.archived_at is not None or policy.status == "archived",
                    "summary": published.summary,
                    "published_at": published.published_at,
                    "published_by": published.published_by,
                    "is_active": published.is_active,
                    "policy_updated_since_published": policy_updated_since_published,
                    "policy_last_updated_at": policy.updated_at,
                }
            )
        return results

    def unpublish_policy(self, org_id: uuid.UUID, policy_id: uuid.UUID, user_id: uuid.UUID) -> TrustCenterPublishedPolicy:
        row = self.db.execute(
            select(TrustCenterPublishedPolicy).where(
                TrustCenterPublishedPolicy.organization_id == org_id,
                TrustCenterPublishedPolicy.policy_id == policy_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Published policy not found")

        row.is_active = False
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="trust_center.policy_unpublished",
            entity_type="trust_center_published_policy",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"policy_id": str(policy_id), "is_active": row.is_active},
            metadata_json={"source": "api"},
        )
        return row

    def _queue_request_notification_to_managers(self, org_id: uuid.UUID, request: TrustCenterAccessRequest) -> int:
        recipients = self.db.execute(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .join(Role, Role.id == Membership.role_id)
            .where(
                Membership.organization_id == org_id,
                Membership.status == "active",
                Role.name == "compliance_manager",
                User.is_active.is_(True),
                User.status == "active",
                User.email.is_not(None),
            )
        ).scalars().all()

        queued = 0
        for user in recipients:
            self.db.add(
                EmailOutbox(
                    organization_id=org_id,
                    template_id=None,
                    event_type="trust_center.access_request.submitted",
                    recipient_email=user.email,
                    recipient_user_id=user.id,
                    subject=f"Trust Center access request from {request.requester_name}",
                    body_text=(
                        f"Requester: {request.requester_name}\n"
                        f"Email: {request.requester_email}\n"
                        f"Company: {request.requester_company or 'N/A'}\n"
                        f"Reason: {request.request_reason or 'N/A'}\n"
                    ),
                    body_html=None,
                    status="pending",
                    priority="normal",
                    scheduled_at=None,
                    queued_at=self.utcnow(),
                    attempt_count=0,
                    max_attempts=3,
                    metadata_json={"request_id": str(request.id), "source": "trust_center"},
                    created_by_user_id=None,
                )
            )
            queued += 1
        return queued

    def submit_access_request(self, org_id: uuid.UUID, data) -> dict:
        config = self._require_config(org_id)
        if not config.is_enabled or not config.request_access_enabled:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trust center not found")

        existing_pending = self.db.execute(
            select(TrustCenterAccessRequest).where(
                TrustCenterAccessRequest.organization_id == org_id,
                TrustCenterAccessRequest.requester_email == data.requester_email,
                TrustCenterAccessRequest.status == "pending",
            )
        ).scalar_one_or_none()
        if existing_pending is not None:
            return {
                "request_id": existing_pending.id,
                "message": "A pending request already exists for this email; it has not been duplicated.",
                "duplicate": True,
            }

        row = TrustCenterAccessRequest(
            organization_id=org_id,
            requester_name=data.requester_name,
            requester_email=data.requester_email,
            requester_company=data.requester_company,
            request_reason=data.request_reason,
            status="pending",
        )
        self.db.add(row)
        self.db.flush()

        self._queue_request_notification_to_managers(org_id, row)

        AuditService(self.db).write_audit_log(
            action="trust_center.access_request_submitted",
            entity_type="trust_center_access_request",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=None,
            after_json={"status": row.status, "requester_email": row.requester_email},
            metadata_json={"source": "public"},
        )

        return {"request_id": row.id, "message": "Request submitted", "duplicate": False}

    def _expire_stale_approved_requests(self, org_id: uuid.UUID) -> None:
        now = self.utcnow()
        stale_rows = self.db.execute(
            select(TrustCenterAccessRequest).where(
                TrustCenterAccessRequest.organization_id == org_id,
                TrustCenterAccessRequest.status == "approved",
                TrustCenterAccessRequest.access_expires_at.is_not(None),
                TrustCenterAccessRequest.access_expires_at < now,
            )
        ).scalars().all()
        for row in stale_rows:
            row.status = "expired"
            row.access_token_hash = None
            AuditService(self.db).write_audit_log(
                action="trust_center.access_request_expired",
                entity_type="trust_center_access_request",
                entity_id=row.id,
                organization_id=org_id,
                actor_user_id=None,
                after_json={"status": row.status},
                metadata_json={"source": "lazy_expiry"},
            )
        if stale_rows:
            self.db.flush()

    def list_access_requests(self, org_id: uuid.UUID, status_value: str | None = None) -> list[TrustCenterAccessRequest]:
        self._expire_stale_approved_requests(org_id)
        stmt = select(TrustCenterAccessRequest).where(TrustCenterAccessRequest.organization_id == org_id)
        if status_value is not None:
            stmt = stmt.where(TrustCenterAccessRequest.status == status_value)
        return self.db.execute(stmt.order_by(TrustCenterAccessRequest.created_at.desc())).scalars().all()

    def review_access_request(
        self,
        org_id: uuid.UUID,
        request_id: uuid.UUID,
        action: str,
        reviewer_id: uuid.UUID,
        notes: str | None = None,
    ) -> TrustCenterAccessRequest:
        row = self._require_access_request(org_id, request_id)
        if row.status != "pending":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only pending requests can be reviewed")

        if action not in {"approve", "reject"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid review action")

        row.reviewed_by = reviewer_id
        row.reviewed_at = self.utcnow()
        row.review_notes = notes

        if action == "approve":
            raw_token = secrets.token_urlsafe(32)
            row.access_token_hash = self._hash_token(raw_token)
            row.access_expires_at = self.utcnow() + timedelta(days=7)
            row.status = "approved"
            subject = "Trust Center access request approved"
            body = (
                "Your request has been approved. "
                f"Access expires at {row.access_expires_at.isoformat() if row.access_expires_at else 'N/A'}."
            )
        else:
            row.status = "rejected"
            row.access_token_hash = None
            row.access_expires_at = None
            subject = "Trust Center access request rejected"
            body = "Your request has been reviewed and rejected."

        self.db.add(
            EmailOutbox(
                organization_id=org_id,
                template_id=None,
                event_type="trust_center.access_request.reviewed",
                recipient_email=row.requester_email,
                recipient_user_id=None,
                subject=subject,
                body_text=body,
                body_html=None,
                status="pending",
                priority="normal",
                scheduled_at=None,
                queued_at=self.utcnow(),
                attempt_count=0,
                max_attempts=3,
                metadata_json={"request_id": str(row.id), "action": action, "source": "trust_center"},
                created_by_user_id=reviewer_id,
            )
        )

        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="trust_center.access_request_reviewed",
            entity_type="trust_center_access_request",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=reviewer_id,
            after_json={"status": row.status, "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None},
            metadata_json={"source": "api", "action": action},
        )
        return row

    def update_uptime_status(self, org_id: uuid.UUID, new_status: str, user_id: uuid.UUID) -> TrustCenterConfiguration:
        row = self._require_config(org_id)
        row.uptime_status = new_status
        row.uptime_updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="trust_center.uptime_updated",
            entity_type="trust_center_configuration",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"uptime_status": row.uptime_status},
            metadata_json={"source": "api"},
        )
        return row
