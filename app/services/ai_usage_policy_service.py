"""AI-Usage Policy Compliance service (T4-17).

Bridges the AI Governance domain (AISystem) and the Policy Management domain
(CompliancePolicy / PolicyAttestationCampaign / PolicyAttestationRecord) via
read-only calls into the existing service/model layers of both. This module
owns only the new `ai_usage_policy_checks` table.

--------------------------------------------------------------------------
DEFINITION OF "COMPLIANT" AT THE ORG LEVEL (read this before touching logic)
--------------------------------------------------------------------------
For a given AI system:

1. Resolve "the" usage policy for it. There is no dedicated policy_type in
   CompliancePolicy for "AI usage" (POLICY_TYPE_PATTERN is limited to
   acceptable_use|data_retention|incident_response|access_control|
   change_management|business_continuity|other), so per-org auto-detection
   uses the convention that an "acceptable_use" policy is the org's AI usage
   policy: the most recently effective, non-archived, approved
   CompliancePolicy with policy_type == 'acceptable_use' (ties broken by
   created_at desc). A policy still in 'draft'/'under_review'/'deprecated'
   status does not count -- only 'approved' is treated as the org's live
   policy, matching the convention used elsewhere for resolving "the"
   effective policy (see kri_calculator.py, inbound_questionnaire_service.py).
   Callers may instead pass an explicit policy_id (e.g. if an org links a
   specific policy per AI-system-category) which always wins, but must still
   itself be 'approved' to count. If no (approved) policy can be resolved at
   all -> 'non_compliant_no_policy'.

2. If a policy is resolved, find its attestation campaigns via
   PolicyAttestationService.list_campaigns(org_id, policy_id=...), newest
   first. If no campaign has ever been created for this policy ->
   'non_compliant_never_attested' (no attestation process has ever run).

3. Take the most recent campaign. Look at PolicyAttestationRecord rows for
   that campaign (org level, not per-user):
     - If ANY record has status == 'attested' AND expires_at is in the
       future (or NULL, meaning never expires) -> 'compliant'.
     - Else if ANY record has status in ('attested', 'expired') (i.e. an
       attestation happened at some point but none is currently valid) ->
       'non_compliant_expired_attestation'.
     - Else (no record was ever attested/expired -- e.g. all pending or
       exempted only, or no records at all) -> 'non_compliant_never_attested'.

This is an org-level (not per-user) determination: attestations are
per-user, but for the purposes of "is this AI system's usage policy
adequately attested," we only need evidence that at least one currently
valid attestation exists against the most recent campaign for that policy.
"""

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.services.policy_attestation_service import PolicyAttestationService
from app.models.ai_system import AISystem
from app.models.ai_usage_policy_check import AiUsagePolicyCheck
from app.models.compliance_policy import CompliancePolicy
from app.models.policy_attestation_record import PolicyAttestationRecord
from app.services.audit_service import AuditService

NON_COMPLIANT_STATUSES = (
    "non_compliant_no_policy",
    "non_compliant_expired_attestation",
    "non_compliant_never_attested",
)


class AiUsagePolicyService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    # ------------------------------------------------------------------
    # AI system lookups
    # ------------------------------------------------------------------
    def _get_active_ai_system(self, org_id: uuid.UUID, ai_system_id: uuid.UUID) -> AISystem:
        row = self.db.execute(
            select(AISystem).where(
                AISystem.organization_id == org_id,
                AISystem.id == ai_system_id,
                AISystem.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system not found")
        if row.archived_at is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI system is archived; not eligible for a usage-policy check")
        return row

    def _list_active_ai_systems(self, org_id: uuid.UUID) -> list[AISystem]:
        return self.db.execute(
            select(AISystem).where(
                AISystem.organization_id == org_id,
                AISystem.deleted_at.is_(None),
                AISystem.archived_at.is_(None),
            )
        ).scalars().all()

    # ------------------------------------------------------------------
    # Policy resolution
    # ------------------------------------------------------------------
    def _resolve_policy(self, org_id: uuid.UUID, policy_id: uuid.UUID | None) -> CompliancePolicy | None:
        # Only an "approved" policy can anchor a compliance determination --
        # a draft/under_review/deprecated policy is not yet the org's live,
        # enforceable policy. This mirrors the same convention used
        # elsewhere in the platform for resolving "the" effective policy
        # (see app/compliance/services/kri_calculator.py and
        # app/compliance/services/inbound_questionnaire_service.py, both of
        # which filter on CompliancePolicy.status == "approved"). Without
        # this filter, an org could have only ever drafted an AI-usage
        # policy (never approved it) and this check would still report
        # "policy exists" -- which is materially misleading for a compliance
        # officer relying on this signal.
        if policy_id is not None:
            return self.db.execute(
                select(CompliancePolicy).where(
                    CompliancePolicy.organization_id == org_id,
                    CompliancePolicy.id == policy_id,
                    CompliancePolicy.archived_at.is_(None),
                    CompliancePolicy.status == "approved",
                )
            ).scalar_one_or_none()

        # Convention: the org's "acceptable_use" policy is treated as its
        # AI-usage policy (see module docstring). Prefer approved, most
        # recently effective / created.
        stmt = (
            select(CompliancePolicy)
            .where(
                CompliancePolicy.organization_id == org_id,
                CompliancePolicy.policy_type == "acceptable_use",
                CompliancePolicy.archived_at.is_(None),
                CompliancePolicy.status == "approved",
            )
            .order_by(CompliancePolicy.created_at.desc())
        )
        return self.db.execute(stmt).scalars().first()

    def _determine_status(
        self, org_id: uuid.UUID, policy: CompliancePolicy | None
    ) -> tuple[str, uuid.UUID | None, str]:
        if policy is None:
            return (
                "non_compliant_no_policy",
                None,
                "No AI-usage-relevant compliance policy (policy_type='acceptable_use') exists for this organization.",
            )

        campaigns = PolicyAttestationService(self.db).list_campaigns(
            org_id, policy_id=policy.id, page=1, page_size=1
        )
        if not campaigns:
            return (
                "non_compliant_never_attested",
                policy.id,
                f"Policy '{policy.title}' exists but no attestation campaign has ever been created for it.",
            )

        campaign = campaigns[0]
        records = self.db.execute(
            select(PolicyAttestationRecord).where(
                PolicyAttestationRecord.organization_id == org_id,
                PolicyAttestationRecord.campaign_id == campaign.id,
            )
        ).scalars().all()

        now = self.utcnow()

        def _is_future(expires_at: datetime | None) -> bool:
            if expires_at is None:
                return True
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            return expires_at > now

        has_current_valid = any(r.status == "attested" and _is_future(r.expires_at) for r in records)
        if has_current_valid:
            return (
                "compliant",
                policy.id,
                f"Policy '{policy.title}' has a currently valid attestation on campaign '{campaign.name}'.",
            )

        has_ever_attested_or_expired = any(r.status in ("attested", "expired") for r in records)
        if has_ever_attested_or_expired:
            return (
                "non_compliant_expired_attestation",
                policy.id,
                f"Policy '{policy.title}' campaign '{campaign.name}' was attested previously but no attestation is currently valid (expired).",
            )

        return (
            "non_compliant_never_attested",
            policy.id,
            f"Policy '{policy.title}' campaign '{campaign.name}' exists but no attestation was ever completed.",
        )

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------
    def run_compliance_check(
        self,
        org_id: uuid.UUID,
        ai_system_id: uuid.UUID,
        policy_id: uuid.UUID | None,
        actor_id: uuid.UUID | None,
    ) -> AiUsagePolicyCheck:
        self._get_active_ai_system(org_id, ai_system_id)
        policy = self._resolve_policy(org_id, policy_id)
        compliance_status, resolved_policy_id, details = self._determine_status(org_id, policy)

        existing = self.db.execute(
            select(AiUsagePolicyCheck).where(
                AiUsagePolicyCheck.organization_id == org_id,
                AiUsagePolicyCheck.ai_system_id == ai_system_id,
            )
        ).scalar_one_or_none()

        now = self.utcnow()
        if existing is not None:
            existing.policy_id = resolved_policy_id
            existing.compliance_status = compliance_status
            existing.last_checked_at = now
            existing.details = details
            existing.created_by = actor_id if actor_id is not None else existing.created_by
            row = existing
        else:
            row = AiUsagePolicyCheck(
                organization_id=org_id,
                ai_system_id=ai_system_id,
                policy_id=resolved_policy_id,
                compliance_status=compliance_status,
                last_checked_at=now,
                details=details,
                created_by=actor_id,
            )
            self.db.add(row)

        self.db.flush()
        return row

    def bulk_run_for_org(self, org_id: uuid.UUID, actor_id: uuid.UUID | None) -> list[AiUsagePolicyCheck]:
        ai_systems = self._list_active_ai_systems(org_id)
        results = []
        for ai_system in ai_systems:
            row = self.run_compliance_check(org_id, ai_system.id, None, actor_id)
            results.append(row)

        AuditService(self.db).write_audit_log(
            action="ai_usage_policy.bulk_run",
            entity_type="ai_usage_policy_check",
            entity_id=None,
            organization_id=org_id,
            actor_user_id=actor_id,
            metadata_json={"ai_system_count": len(ai_systems)},
        )
        return results

    # ------------------------------------------------------------------
    # Read APIs
    # ------------------------------------------------------------------
    def get_summary(self, org_id: uuid.UUID) -> dict:
        rows = self.db.execute(
            select(AiUsagePolicyCheck).where(AiUsagePolicyCheck.organization_id == org_id)
        ).scalars().all()
        by_status: dict[str, int] = {}
        for row in rows:
            by_status[row.compliance_status] = by_status.get(row.compliance_status, 0) + 1
        return {"total_checked": len(rows), "by_status": by_status}

    def get_gaps(self, org_id: uuid.UUID) -> list[dict]:
        rows = self.db.execute(
            select(AiUsagePolicyCheck, AISystem)
            .join(AISystem, AISystem.id == AiUsagePolicyCheck.ai_system_id)
            .where(
                AiUsagePolicyCheck.organization_id == org_id,
                AiUsagePolicyCheck.compliance_status.in_(NON_COMPLIANT_STATUSES),
                AISystem.archived_at.is_(None),
                AISystem.deleted_at.is_(None),
            )
        ).all()

        gaps = []
        for check, ai_system in rows:
            gaps.append(
                {
                    "ai_system_id": ai_system.id,
                    "ai_system_name": ai_system.name,
                    "policy_id": check.policy_id,
                    "compliance_status": check.compliance_status,
                    "reason": check.details or check.compliance_status,
                    "last_checked_at": check.last_checked_at,
                }
            )
        return gaps

    def get_latest_check(self, org_id: uuid.UUID, ai_system_id: uuid.UUID) -> AiUsagePolicyCheck:
        row = self.db.execute(
            select(AiUsagePolicyCheck).where(
                AiUsagePolicyCheck.organization_id == org_id,
                AiUsagePolicyCheck.ai_system_id == ai_system_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No usage-policy check found for this AI system")
        return row
