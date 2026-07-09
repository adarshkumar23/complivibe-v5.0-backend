import hashlib
import json
import uuid
from datetime import UTC, date, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.compliance_policy import CompliancePolicy
from app.models.compliance_policy_version import CompliancePolicyVersion
from app.models.membership import Membership
from app.models.policy_attestation import PolicyAttestation
from app.models.policy_attestation_campaign import PolicyAttestationCampaign
from app.models.policy_attestation_record import PolicyAttestationRecord
from app.models.user import User
from app.services.audit_service import AuditService


class PolicyAttestationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _policy_in_org(self, org_id: uuid.UUID, policy_id: uuid.UUID) -> CompliancePolicy:
        row = self.db.execute(
            select(CompliancePolicy).where(
                CompliancePolicy.organization_id == org_id,
                CompliancePolicy.id == policy_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
        return row

    def _campaign_in_org(self, org_id: uuid.UUID, campaign_id: uuid.UUID) -> PolicyAttestationCampaign:
        row = self.db.execute(
            select(PolicyAttestationCampaign).where(
                PolicyAttestationCampaign.organization_id == org_id,
                PolicyAttestationCampaign.id == campaign_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
        return row

    def _resolve_attestation_text(
        self,
        policy: CompliancePolicy,
        *,
        attestation_text: str | None,
        policy_version_id: uuid.UUID | None,
    ) -> tuple[str, uuid.UUID | None]:
        if attestation_text:
            return attestation_text, policy_version_id

        if policy_version_id is not None:
            version_row = self.db.execute(
                select(CompliancePolicyVersion).where(
                    CompliancePolicyVersion.id == policy_version_id,
                    CompliancePolicyVersion.organization_id == policy.organization_id,
                    CompliancePolicyVersion.policy_id == policy.id,
                )
            ).scalar_one_or_none()
            if version_row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy version not found")
            return json.dumps(version_row.content_snapshot_json, separators=(",", ":"), sort_keys=True), version_row.id

        if policy.content_url:
            return policy.content_url, None
        return f"Policy: {policy.title}", None

    def _active_org_members(self, org_id: uuid.UUID) -> list[uuid.UUID]:
        rows = self.db.execute(
            select(Membership.user_id)
            .join(User, User.id == Membership.user_id)
            .where(
                Membership.organization_id == org_id,
                Membership.status == "active",
                User.is_active.is_(True),
                User.status == "active",
            )
        ).all()
        return [r[0] for r in rows]

    def create_campaign(
        self,
        org_id: uuid.UUID,
        policy_id: uuid.UUID,
        title: str,
        description: str | None,
        due_date: date,
        created_by: uuid.UUID,
        *,
        attestation_text: str | None = None,
        policy_version_id: uuid.UUID | None = None,
        user_ids: list[uuid.UUID] | None = None,
    ) -> tuple[PolicyAttestationCampaign, int]:
        policy = self._policy_in_org(org_id, policy_id)
        text_shown, resolved_policy_version_id = self._resolve_attestation_text(
            policy,
            attestation_text=attestation_text,
            policy_version_id=policy_version_id,
        )
        content_hash = hashlib.sha256(text_shown.encode()).hexdigest()

        campaign = PolicyAttestationCampaign(
            organization_id=org_id,
            policy_id=policy_id,
            policy_version_id=resolved_policy_version_id,
            policy_version=policy.version,
            title=title,
            name=title,
            description=description,
            attestation_text_shown=text_shown,
            content_hash=content_hash,
            due_date=due_date,
            status="active",
            created_by=created_by,
            attestation_expiry_days=365,
        )
        self.db.add(campaign)
        self.db.flush()

        members = user_ids if user_ids else self._active_org_members(org_id)
        deduped_member_ids = list(dict.fromkeys(members))

        if deduped_member_ids:
            self.db.add_all(
                [
                    PolicyAttestation(
                        organization_id=org_id,
                        campaign_id=campaign.id,
                        user_id=user_id,
                        status="pending",
                    )
                    for user_id in deduped_member_ids
                ]
            )
            # Backward compatibility for existing A31 feature/tests.
            self.db.add_all(
                [
                    PolicyAttestationRecord(
                        organization_id=org_id,
                        campaign_id=campaign.id,
                        user_id=user_id,
                        status="pending",
                    )
                    for user_id in deduped_member_ids
                ]
            )
            self.db.flush()

        AuditService(self.db).write_audit_log(
            action="attestation.campaign_created",
            entity_type="policy_attestation_campaign",
            entity_id=campaign.id,
            organization_id=org_id,
            actor_user_id=created_by,
            metadata_json={
                "policy_id": str(policy_id),
                "member_count": len(deduped_member_ids),
                "due_date": due_date.isoformat(),
                "content_hash": content_hash,
            },
        )
        return campaign, len(deduped_member_ids)

    def _policy_changed_since_campaign_start(self, campaign: PolicyAttestationCampaign) -> tuple[bool, str | None]:
        """Detect drift between the policy text a campaign asked employees to attest to and the
        policy's current live version. This must never be silently swallowed: if the policy has
        moved on (re-approved, re-versioned) since the campaign launched, in-flight and even
        already-completed attestations may no longer reflect what's actually in force.
        """
        policy = self.db.execute(
            select(CompliancePolicy).where(
                CompliancePolicy.organization_id == campaign.organization_id,
                CompliancePolicy.id == campaign.policy_id,
            )
        ).scalar_one_or_none()
        if policy is None:
            return False, None

        changed = campaign.policy_version != policy.version

        if not changed and campaign.policy_version_id is not None:
            version_row = self.db.execute(
                select(CompliancePolicyVersion.status).where(CompliancePolicyVersion.id == campaign.policy_version_id)
            ).scalar_one_or_none()
            if version_row is not None and version_row != "approved":
                changed = True

        return changed, policy.version

    def get_campaign_summary(self, org_id: uuid.UUID, campaign_id: uuid.UUID) -> dict:
        campaign = self._campaign_in_org(org_id, campaign_id)
        policy_changed, current_policy_version = self._policy_changed_since_campaign_start(campaign)
        rows = self.db.execute(
            select(PolicyAttestation.status, func.count(PolicyAttestation.id))
            .where(
                PolicyAttestation.organization_id == org_id,
                PolicyAttestation.campaign_id == campaign_id,
            )
            .group_by(PolicyAttestation.status)
        ).all()
        counts = {status_key: int(count) for status_key, count in rows}
        total_members = int(sum(counts.values()))
        attested_count = counts.get("attested", 0)
        declined_count = counts.get("declined", 0)
        pending_count = counts.get("pending", 0)
        completion_pct = round(((attested_count + declined_count) / total_members) * 100, 2) if total_members > 0 else 0.0

        return {
            "campaign": campaign,
            "total_members": total_members,
            "attested_count": attested_count,
            "declined_count": declined_count,
            "pending_count": pending_count,
            "completion_pct": completion_pct,
            "policy_changed_since_campaign_start": policy_changed,
            "current_policy_version": current_policy_version,
        }

    def _get_user_attestation(self, org_id: uuid.UUID, campaign_id: uuid.UUID, user_id: uuid.UUID) -> PolicyAttestation:
        row = self.db.execute(
            select(PolicyAttestation).where(
                PolicyAttestation.organization_id == org_id,
                PolicyAttestation.campaign_id == campaign_id,
                PolicyAttestation.user_id == user_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attestation not found")
        return row

    def attest(self, org_id: uuid.UUID, campaign_id: uuid.UUID, user_id: uuid.UUID, ip_address: str | None = None) -> PolicyAttestation:
        row = self._get_user_attestation(org_id, campaign_id, user_id)
        if row.status != "pending":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Attestation already finalized")

        row.status = "attested"
        row.attested_at = self.utcnow()
        row.ip_address = ip_address

        legacy = self.db.execute(
            select(PolicyAttestationRecord).where(
                PolicyAttestationRecord.organization_id == org_id,
                PolicyAttestationRecord.campaign_id == campaign_id,
                PolicyAttestationRecord.user_id == user_id,
            )
        ).scalar_one_or_none()
        if legacy is not None and legacy.status == "pending":
            legacy.status = "attested"
            legacy.attested_at = row.attested_at

        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="attestation.attested",
            entity_type="policy_attestation",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            metadata_json={"campaign_id": str(campaign_id)},
            ip_address=ip_address,
        )
        return row

    def decline(
        self,
        org_id: uuid.UUID,
        campaign_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        decline_reason: str | None = None,
        ip_address: str | None = None,
    ) -> PolicyAttestation:
        row = self._get_user_attestation(org_id, campaign_id, user_id)
        if row.status != "pending":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Attestation already finalized")

        row.status = "declined"
        row.declined_at = self.utcnow()
        row.decline_reason = decline_reason
        row.ip_address = ip_address

        legacy = self.db.execute(
            select(PolicyAttestationRecord).where(
                PolicyAttestationRecord.organization_id == org_id,
                PolicyAttestationRecord.campaign_id == campaign_id,
                PolicyAttestationRecord.user_id == user_id,
            )
        ).scalar_one_or_none()
        if legacy is not None and legacy.status == "pending":
            # This is the completion-tracking table dashboards/reports actually read
            # (see employee_attestation_service, experience_service,
            # custom_report_generator) -- keep it in sync the same way attest() does,
            # so a decline doesn't stay stuck showing as "pending" forever.
            legacy.status = "declined"

        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="attestation.declined",
            entity_type="policy_attestation",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            metadata_json={"campaign_id": str(campaign_id), "decline_reason": decline_reason},
            ip_address=ip_address,
        )
        return row

    def list_campaigns(
        self,
        org_id: uuid.UUID,
        *,
        policy_id: uuid.UUID | None = None,
        status_value: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[PolicyAttestationCampaign]:
        stmt = select(PolicyAttestationCampaign).where(PolicyAttestationCampaign.organization_id == org_id)
        if policy_id is not None:
            stmt = stmt.where(PolicyAttestationCampaign.policy_id == policy_id)
        if status_value is not None:
            stmt = stmt.where(PolicyAttestationCampaign.status == status_value)

        stmt = stmt.order_by(PolicyAttestationCampaign.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        return self.db.execute(stmt).scalars().all()

    def list_campaign_attestations(self, org_id: uuid.UUID, campaign_id: uuid.UUID) -> list[PolicyAttestation]:
        self._campaign_in_org(org_id, campaign_id)
        return self.db.execute(
            select(PolicyAttestation)
            .where(
                PolicyAttestation.organization_id == org_id,
                PolicyAttestation.campaign_id == campaign_id,
            )
            .order_by(PolicyAttestation.created_at.desc())
        ).scalars().all()

    def list_user_attestations(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        status_value: str | None = None,
    ) -> list[PolicyAttestation]:
        stmt = select(PolicyAttestation).where(
            PolicyAttestation.organization_id == org_id,
            PolicyAttestation.user_id == user_id,
        )
        if status_value is not None:
            stmt = stmt.where(PolicyAttestation.status == status_value)
        return self.db.execute(stmt.order_by(PolicyAttestation.created_at.desc())).scalars().all()
