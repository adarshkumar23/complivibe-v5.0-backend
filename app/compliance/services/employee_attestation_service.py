import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.compliance_policy import CompliancePolicy
from app.models.membership import Membership
from app.models.policy_attestation_campaign import PolicyAttestationCampaign
from app.models.policy_attestation_record import PolicyAttestationRecord
from app.models.user import User
from app.schemas.attestation import AttestationCampaignCreate, AttestationCampaignUpdate
from app.services.audit_service import AuditService
from app.services.email_service import EmailService
from app.services.rbac_service import RBACService
from app.services.seed_service import SeedService


class AttestationCampaignService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def utcdate() -> date:
        return datetime.now(UTC).date()

    def require_policy_in_org(self, org_id: uuid.UUID, policy_id: uuid.UUID) -> CompliancePolicy:
        row = self.db.execute(
            select(CompliancePolicy).where(
                CompliancePolicy.organization_id == org_id,
                CompliancePolicy.id == policy_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compliance policy not found")
        return row

    def require_campaign(self, org_id: uuid.UUID, campaign_id: uuid.UUID) -> PolicyAttestationCampaign:
        row = self.db.execute(
            select(PolicyAttestationCampaign).where(
                PolicyAttestationCampaign.organization_id == org_id,
                PolicyAttestationCampaign.id == campaign_id,
                PolicyAttestationCampaign.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attestation campaign not found")
        return row

    def _require_active_member_user(self, org_id: uuid.UUID, user_id: uuid.UUID) -> User:
        membership = self.db.execute(
            select(Membership).where(
                Membership.organization_id == org_id,
                Membership.user_id == user_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="All users must be active org members")

        user = self.db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if user is None or not user.is_active or user.status != "active":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="All users must be active org members")
        return user

    def _campaign_counts(self, org_id: uuid.UUID, campaign_id: uuid.UUID) -> dict[str, int]:
        rows = self.db.execute(
            select(PolicyAttestationRecord.status, func.count(PolicyAttestationRecord.id))
            .where(
                PolicyAttestationRecord.organization_id == org_id,
                PolicyAttestationRecord.campaign_id == campaign_id,
            )
            .group_by(PolicyAttestationRecord.status)
        ).all()
        counts = {str(status_key): int(count) for status_key, count in rows}
        total = int(sum(counts.values()))
        return {
            "total_assigned": total,
            "attested_count": counts.get("attested", 0),
            "declined_count": counts.get("declined", 0),
            "pending_count": counts.get("pending", 0),
            "expired_count": counts.get("expired", 0),
            "exempted_count": counts.get("exempted", 0),
        }

    @staticmethod
    def _completion_rate(*, attested_count: int, total_assigned: int) -> float:
        if total_assigned <= 0:
            return 0.0
        return round((attested_count / total_assigned) * 100.0, 2)

    def _policy_changed_since_campaign_start(self, campaign: PolicyAttestationCampaign) -> tuple[bool, str | None]:
        """Compare the policy version a campaign asked employees to attest to against the
        policy's current live version. Never let a campaign silently look "complete" against a
        policy that has since been re-versioned out from under it.
        """
        policy = self.db.execute(
            select(CompliancePolicy).where(
                CompliancePolicy.organization_id == campaign.organization_id,
                CompliancePolicy.id == campaign.policy_id,
            )
        ).scalar_one_or_none()
        if policy is None:
            return False, None
        return campaign.policy_version != policy.version, policy.version

    def campaign_with_stats(self, campaign: PolicyAttestationCampaign) -> dict:
        counts = self._campaign_counts(campaign.organization_id, campaign.id)
        policy_changed, current_policy_version = self._policy_changed_since_campaign_start(campaign)
        return {
            "id": campaign.id,
            "organization_id": campaign.organization_id,
            "policy_id": campaign.policy_id,
            "policy_version": campaign.policy_version,
            "name": campaign.name,
            "description": campaign.description,
            "due_date": campaign.due_date,
            "attestation_expiry_days": campaign.attestation_expiry_days,
            "status": campaign.status,
            "created_by": campaign.created_by,
            "created_at": campaign.created_at,
            "updated_at": campaign.updated_at,
            **counts,
            "completion_rate": self._completion_rate(
                attested_count=counts["attested_count"],
                total_assigned=counts["total_assigned"],
            ),
            "policy_changed_since_campaign_start": policy_changed,
            "current_policy_version": current_policy_version,
        }

    def _sync_campaign_completed_status(self, campaign: PolicyAttestationCampaign) -> None:
        if campaign.status != "active":
            return
        counts = self._campaign_counts(campaign.organization_id, campaign.id)
        if counts["total_assigned"] > 0 and counts["pending_count"] == 0:
            campaign.status = "completed"
            self.db.flush()

    def create_campaign(
        self,
        org_id: uuid.UUID,
        payload: AttestationCampaignCreate,
        created_by: uuid.UUID,
    ) -> tuple[PolicyAttestationCampaign, int]:
        self.require_policy_in_org(org_id, payload.policy_id)

        existing_name = self.db.execute(
            select(PolicyAttestationCampaign.id).where(
                PolicyAttestationCampaign.organization_id == org_id,
                PolicyAttestationCampaign.name == payload.name,
                PolicyAttestationCampaign.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if existing_name is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Attestation campaign name already exists")

        user_ids = list(dict.fromkeys(payload.user_ids))
        for user_id in user_ids:
            self._require_active_member_user(org_id, user_id)

        campaign = PolicyAttestationCampaign(
            organization_id=org_id,
            policy_id=payload.policy_id,
            policy_version=payload.policy_version,
            name=payload.name,
            description=payload.description,
            due_date=payload.due_date,
            attestation_expiry_days=payload.attestation_expiry_days,
            status="active",
            created_by=created_by,
        )
        self.db.add(campaign)
        self.db.flush()

        records = [
            PolicyAttestationRecord(
                organization_id=org_id,
                campaign_id=campaign.id,
                user_id=user_id,
                status="pending",
            )
            for user_id in user_ids
        ]
        if records:
            self.db.add_all(records)
            self.db.flush()

        AuditService(self.db).write_audit_log(
            action="attestation.campaign_created",
            entity_type="policy_attestation_campaign",
            entity_id=campaign.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={
                "policy_id": str(campaign.policy_id),
                "policy_version": campaign.policy_version,
                "name": campaign.name,
                "due_date": str(campaign.due_date),
                "record_count_created": len(records),
            },
            metadata_json={"source": "api"},
        )
        return campaign, len(records)

    def list_campaigns(
        self,
        org_id: uuid.UUID,
        *,
        policy_id: uuid.UUID | None = None,
        status_value: str | None = None,
    ) -> list[PolicyAttestationCampaign]:
        stmt = select(PolicyAttestationCampaign).where(
            PolicyAttestationCampaign.organization_id == org_id,
            PolicyAttestationCampaign.deleted_at.is_(None),
        )
        if policy_id is not None:
            stmt = stmt.where(PolicyAttestationCampaign.policy_id == policy_id)
        if status_value is not None:
            stmt = stmt.where(PolicyAttestationCampaign.status == status_value)
        return self.db.execute(stmt.order_by(PolicyAttestationCampaign.created_at.desc())).scalars().all()

    def get_campaign(self, org_id: uuid.UUID, campaign_id: uuid.UUID) -> PolicyAttestationCampaign:
        campaign = self.require_campaign(org_id, campaign_id)
        self._sync_campaign_completed_status(campaign)
        return campaign

    def update_campaign(
        self,
        org_id: uuid.UUID,
        campaign_id: uuid.UUID,
        payload: AttestationCampaignUpdate,
        actor_id: uuid.UUID,
    ) -> PolicyAttestationCampaign:
        campaign = self.require_campaign(org_id, campaign_id)
        if campaign.status == "cancelled":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cancelled campaign cannot be updated")

        updates = payload.model_dump(exclude_unset=True)
        before = {
            "name": campaign.name,
            "description": campaign.description,
            "due_date": str(campaign.due_date),
        }
        for field, value in updates.items():
            setattr(campaign, field, value)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="attestation.campaign_updated",
            entity_type="policy_attestation_campaign",
            entity_id=campaign.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            before_json=before,
            after_json={
                "name": campaign.name,
                "description": campaign.description,
                "due_date": str(campaign.due_date),
            },
            metadata_json={"source": "api"},
        )
        return campaign

    def cancel_campaign(self, org_id: uuid.UUID, campaign_id: uuid.UUID, actor_id: uuid.UUID) -> PolicyAttestationCampaign:
        campaign = self.require_campaign(org_id, campaign_id)
        before = {"status": campaign.status, "deleted_at": campaign.deleted_at.isoformat() if campaign.deleted_at else None}
        campaign.status = "cancelled"
        campaign.deleted_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="attestation.campaign_cancelled",
            entity_type="policy_attestation_campaign",
            entity_id=campaign.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            before_json=before,
            after_json={"status": campaign.status, "deleted_at": campaign.deleted_at.isoformat()},
            metadata_json={"source": "api"},
        )
        return campaign

    def get_campaign_completion(self, org_id: uuid.UUID, campaign_id: uuid.UUID) -> list[dict]:
        campaign = self.require_campaign(org_id, campaign_id)
        rows = self.db.execute(
            select(PolicyAttestationRecord, User)
            .join(User, User.id == PolicyAttestationRecord.user_id)
            .where(
                PolicyAttestationRecord.organization_id == org_id,
                PolicyAttestationRecord.campaign_id == campaign.id,
            )
            .order_by(User.email.asc())
        ).all()
        today = self.utcdate()
        return [
            {
                "user_id": user.id,
                "name": user.full_name or user.email,
                "email": user.email,
                "status": record.status,
                "attested_at": record.attested_at,
                "expires_at": record.expires_at,
                "reminder_sent_at": record.reminder_sent_at,
                "days_overdue": (today - campaign.due_date).days
                if record.status == "pending" and campaign.due_date < today
                else None,
            }
            for record, user in rows
        ]

    def get_policy_completion_rate(self, org_id: uuid.UUID, policy_id: uuid.UUID) -> dict:
        self.require_policy_in_org(org_id, policy_id)
        campaigns = self.db.execute(
            select(PolicyAttestationCampaign)
            .where(
                PolicyAttestationCampaign.organization_id == org_id,
                PolicyAttestationCampaign.policy_id == policy_id,
                PolicyAttestationCampaign.deleted_at.is_(None),
                PolicyAttestationCampaign.status == "active",
            )
            .order_by(PolicyAttestationCampaign.created_at.desc())
        ).scalars().all()

        if not campaigns:
            return {
                "policy_id": policy_id,
                "overall_completion_rate": 0.0,
                "campaigns_count": 0,
                "most_recent_campaign_id": None,
                "overdue_count": 0,
            }

        campaign_ids = [row.id for row in campaigns]
        totals = self.db.execute(
            select(PolicyAttestationRecord.status, func.count(PolicyAttestationRecord.id))
            .where(
                PolicyAttestationRecord.organization_id == org_id,
                PolicyAttestationRecord.campaign_id.in_(campaign_ids),
            )
            .group_by(PolicyAttestationRecord.status)
        ).all()
        counts = {str(status_key): int(count) for status_key, count in totals}
        total = int(sum(counts.values()))
        attested = counts.get("attested", 0)

        overdue_count = int(
            self.db.execute(
                select(func.count(PolicyAttestationRecord.id))
                .join(PolicyAttestationCampaign, PolicyAttestationCampaign.id == PolicyAttestationRecord.campaign_id)
                .where(
                    PolicyAttestationRecord.organization_id == org_id,
                    PolicyAttestationCampaign.organization_id == org_id,
                    PolicyAttestationCampaign.policy_id == policy_id,
                    PolicyAttestationCampaign.deleted_at.is_(None),
                    PolicyAttestationCampaign.status == "active",
                    PolicyAttestationRecord.status == "pending",
                    PolicyAttestationCampaign.due_date < self.utcdate(),
                )
            ).scalar_one()
        )

        return {
            "policy_id": policy_id,
            "overall_completion_rate": self._completion_rate(attested_count=attested, total_assigned=total),
            "campaigns_count": len(campaigns),
            "most_recent_campaign_id": campaigns[0].id if campaigns else None,
            "overdue_count": overdue_count,
        }

    def get_dashboard(self, org_id: uuid.UUID) -> dict:
        campaigns = self.list_campaigns(org_id, status_value="active")
        if not campaigns:
            return {
                "active_campaigns": 0,
                "overdue_campaigns": 0,
                "overall_completion_rate": 0.0,
                "pending_attestations_count": 0,
                "campaigns_expiring_soon": [],
            }

        active_campaigns = len(campaigns)
        today = self.utcdate()
        soon_end = today + timedelta(days=7)

        overall_total = 0
        overall_attested = 0
        overdue_campaigns = 0
        pending_attestations_count = 0
        campaigns_expiring_soon: list[PolicyAttestationCampaign] = []

        for campaign in campaigns:
            counts = self._campaign_counts(org_id, campaign.id)
            overall_total += counts["total_assigned"]
            overall_attested += counts["attested_count"]
            pending_attestations_count += counts["pending_count"]
            if campaign.due_date < today and counts["pending_count"] > 0:
                overdue_campaigns += 1
            if today <= campaign.due_date <= soon_end and counts["pending_count"] > 0:
                campaigns_expiring_soon.append(campaign)

        return {
            "active_campaigns": active_campaigns,
            "overdue_campaigns": overdue_campaigns,
            "overall_completion_rate": self._completion_rate(attested_count=overall_attested, total_assigned=overall_total),
            "pending_attestations_count": pending_attestations_count,
            "campaigns_expiring_soon": [self.campaign_with_stats(row) for row in campaigns_expiring_soon],
        }


class AttestationRecordService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.campaign_service = AttestationCampaignService(db)

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _require_record(
        self,
        *,
        org_id: uuid.UUID,
        campaign_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> tuple[PolicyAttestationCampaign, PolicyAttestationRecord]:
        campaign = self.campaign_service.require_campaign(org_id, campaign_id)
        row = self.db.execute(
            select(PolicyAttestationRecord).where(
                PolicyAttestationRecord.organization_id == org_id,
                PolicyAttestationRecord.campaign_id == campaign_id,
                PolicyAttestationRecord.user_id == user_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attestation record not found")
        return campaign, row

    def submit_attestation(
        self,
        org_id: uuid.UUID,
        campaign_id: uuid.UUID,
        user_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> PolicyAttestationRecord:
        campaign, row = self._require_record(org_id=org_id, campaign_id=campaign_id, user_id=user_id)
        if campaign.status == "cancelled":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Campaign is cancelled")
        if row.status == "exempted":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Exempted user cannot attest")
        if row.status != "pending":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attestation record is not pending")

        now = self.utcnow()
        row.status = "attested"
        row.attested_at = now
        row.expires_at = now + timedelta(days=campaign.attestation_expiry_days)
        self.db.flush()
        self.campaign_service._sync_campaign_completed_status(campaign)

        AuditService(self.db).write_audit_log(
            action="attestation.submitted",
            entity_type="policy_attestation_record",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            after_json={
                "campaign_id": str(campaign.id),
                "user_id": str(user_id),
                "status": row.status,
                "attested_at": row.attested_at.isoformat() if row.attested_at else None,
                "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            },
            metadata_json={"source": "api"},
        )
        return row

    def exempt_user(
        self,
        org_id: uuid.UUID,
        campaign_id: uuid.UUID,
        user_id: uuid.UUID,
        reason: str,
        actor_id: uuid.UUID,
    ) -> PolicyAttestationRecord:
        has_manage = RBACService.user_has_permission(self.db, actor_id, org_id, "attestations:manage")
        if not has_manage:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing required permission: attestations:manage")

        campaign, row = self._require_record(org_id=org_id, campaign_id=campaign_id, user_id=user_id)
        if campaign.status == "cancelled":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Campaign is cancelled")
        if row.status != "pending":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending attestations can be exempted")

        row.status = "exempted"
        row.exemption_reason = reason
        row.exempted_by = actor_id
        row.attested_at = None
        row.expires_at = None
        self.db.flush()
        self.campaign_service._sync_campaign_completed_status(campaign)

        AuditService(self.db).write_audit_log(
            action="attestation.user_exempted",
            entity_type="policy_attestation_record",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            after_json={
                "campaign_id": str(campaign.id),
                "user_id": str(user_id),
                "status": row.status,
                "exemption_reason": row.exemption_reason,
            },
            metadata_json={"source": "api"},
        )
        return row

    def _queue_reminder_email(self, *, org_id: uuid.UUID, user: User, campaign: PolicyAttestationCampaign, actor_id: uuid.UUID) -> None:
        if not user.email:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="User has no email")
        SeedService.ensure_global_email_templates(self.db)
        email_service = EmailService(self.db)
        template = email_service.resolve_template_for_org(
            organization_id=org_id,
            template_id=None,
            template_key="task_assigned",
        )
        email_service.queue_email(
            organization_id=org_id,
            template=template,
            event_type="attestation.reminder",
            recipient_email=user.email,
            recipient_user_id=user.id,
            priority="normal",
            scheduled_at=None,
            metadata_json={"source": "attestation_campaign", "campaign_id": str(campaign.id)},
            created_by_user_id=actor_id,
            variables_json={
                "user_name": user.full_name or user.email,
                "task_title": f"Policy attestation due: {campaign.name}",
            },
            initial_status="pending",
        )

    def send_reminder(
        self,
        org_id: uuid.UUID,
        campaign_id: uuid.UUID,
        user_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> PolicyAttestationRecord:
        campaign, row = self._require_record(org_id=org_id, campaign_id=campaign_id, user_id=user_id)
        if row.status != "pending":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending records can be reminded")

        user = self.db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if user is None or not user.is_active:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="User is not active")

        self._queue_reminder_email(org_id=org_id, user=user, campaign=campaign, actor_id=actor_id)
        row.reminder_sent_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="attestation.reminder_sent",
            entity_type="policy_attestation_record",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            after_json={
                "campaign_id": str(campaign.id),
                "user_id": str(user_id),
                "reminder_sent_at": row.reminder_sent_at.isoformat() if row.reminder_sent_at else None,
            },
            metadata_json={"source": "api"},
        )
        return row

    def send_bulk_reminders(self, org_id: uuid.UUID, campaign_id: uuid.UUID, actor_id: uuid.UUID) -> int:
        campaign = self.campaign_service.require_campaign(org_id, campaign_id)
        pending = self.db.execute(
            select(PolicyAttestationRecord, User)
            .join(User, User.id == PolicyAttestationRecord.user_id)
            .where(
                PolicyAttestationRecord.organization_id == org_id,
                PolicyAttestationRecord.campaign_id == campaign.id,
                PolicyAttestationRecord.status == "pending",
            )
        ).all()

        sent = 0
        now = self.utcnow()
        for record, user in pending:
            # is_system_account as well as is_active: enrolment already excludes it, so
            # a record here would be historical, but a reminder must not be counted as
            # "sent" to a principal that cannot read one.
            if not user.is_active or not user.email or user.is_system_account:
                continue
            self._queue_reminder_email(org_id=org_id, user=user, campaign=campaign, actor_id=actor_id)
            record.reminder_sent_at = now
            sent += 1

            AuditService(self.db).write_audit_log(
                action="attestation.reminder_sent",
                entity_type="policy_attestation_record",
                entity_id=record.id,
                organization_id=org_id,
                actor_user_id=actor_id,
                after_json={
                    "campaign_id": str(campaign.id),
                    "user_id": str(record.user_id),
                    "reminder_sent_at": record.reminder_sent_at.isoformat() if record.reminder_sent_at else None,
                },
                metadata_json={"source": "api"},
            )

        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="attestation.bulk_reminder_sent",
            entity_type="policy_attestation_campaign",
            entity_id=campaign.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            after_json={"reminders_queued": sent},
            metadata_json={"source": "api"},
        )
        return sent

    def expire_attestations(self, org_id: uuid.UUID | None = None) -> int:
        now = self.utcnow()
        stmt = select(PolicyAttestationRecord).where(
            PolicyAttestationRecord.status == "attested",
            PolicyAttestationRecord.expires_at.is_not(None),
            PolicyAttestationRecord.expires_at < now,
        )
        if org_id is not None:
            stmt = stmt.where(PolicyAttestationRecord.organization_id == org_id)

        rows = self.db.execute(stmt).scalars().all()
        for row in rows:
            row.status = "expired"
            self.db.flush()
            AuditService(self.db).write_audit_log(
                action="attestation.expired",
                entity_type="policy_attestation_record",
                entity_id=row.id,
                organization_id=row.organization_id,
                actor_user_id=None,
                after_json={"status": row.status, "expires_at": row.expires_at.isoformat() if row.expires_at else None},
                metadata_json={"source": "sweep"},
            )
        return len(rows)

    def get_user_attestations(self, org_id: uuid.UUID, user_id: uuid.UUID) -> list[tuple[PolicyAttestationRecord, PolicyAttestationCampaign, CompliancePolicy]]:
        return self.db.execute(
            select(PolicyAttestationRecord, PolicyAttestationCampaign, CompliancePolicy)
            .join(PolicyAttestationCampaign, PolicyAttestationCampaign.id == PolicyAttestationRecord.campaign_id)
            .join(CompliancePolicy, CompliancePolicy.id == PolicyAttestationCampaign.policy_id)
            .where(
                PolicyAttestationRecord.organization_id == org_id,
                PolicyAttestationRecord.user_id == user_id,
                PolicyAttestationCampaign.organization_id == org_id,
            )
            .order_by(PolicyAttestationRecord.created_at.desc())
        ).all()
