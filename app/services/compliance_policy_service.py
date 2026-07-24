import difflib
import hashlib
import json
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.control import Control
from app.models.compliance_policy import CompliancePolicy
from app.models.compliance_policy_approval_request import CompliancePolicyApprovalRequest
from app.models.compliance_policy_version import CompliancePolicyVersion
from app.models.membership import Membership
from app.models.policy_attestation_campaign import PolicyAttestationCampaign
from app.models.user import User

POLICY_STATUSES = {"draft", "under_review", "approved", "deprecated", "archived"}
POLICY_TYPES = {
    "acceptable_use",
    "data_retention",
    "incident_response",
    "access_control",
    "change_management",
    "business_continuity",
    "other",
}
POLICY_VERSION_STATUSES = {"draft", "submitted", "approved", "rejected", "superseded"}
APPROVAL_REQUEST_STATUSES = {"pending", "approved", "rejected", "cancelled"}
NEXT_STATUS: dict[str, str] = {
    "draft": "under_review",
    "under_review": "approved",
    "approved": "deprecated",
    "deprecated": "archived",
}


class CompliancePolicyService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def require_policy_in_org(self, organization_id: uuid.UUID, policy_id: uuid.UUID) -> CompliancePolicy:
        row = self.db.execute(
            select(CompliancePolicy).where(
                CompliancePolicy.id == policy_id,
                CompliancePolicy.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compliance policy not found")
        return row

    def require_version_in_org(
        self,
        organization_id: uuid.UUID,
        policy_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> CompliancePolicyVersion:
        row = self.db.execute(
            select(CompliancePolicyVersion).where(
                CompliancePolicyVersion.id == version_id,
                CompliancePolicyVersion.organization_id == organization_id,
                CompliancePolicyVersion.policy_id == policy_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compliance policy version not found")
        return row

    def require_approval_request_in_org(
        self,
        organization_id: uuid.UUID,
        policy_id: uuid.UUID,
        request_id: uuid.UUID,
    ) -> CompliancePolicyApprovalRequest:
        row = self.db.execute(
            select(CompliancePolicyApprovalRequest).where(
                CompliancePolicyApprovalRequest.id == request_id,
                CompliancePolicyApprovalRequest.organization_id == organization_id,
                CompliancePolicyApprovalRequest.policy_id == policy_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compliance policy approval request not found")
        return row

    def ensure_active_member(self, organization_id: uuid.UUID, user_id: uuid.UUID, *, field_name: str) -> User:
        membership = self.db.execute(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.user_id == user_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{field_name} must be an active member of the organization",
            )

        user = self.db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if user is None or not user.is_active or user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{field_name} must be an active member of the organization",
            )
        return user

    def ensure_owner_is_active_member(self, organization_id: uuid.UUID, owner_user_id: uuid.UUID) -> User:
        return self.ensure_active_member(organization_id, owner_user_id, field_name="owner_user_id")

    def require_control_in_org(self, organization_id: uuid.UUID, control_id: uuid.UUID) -> Control:
        row = self.db.execute(
            select(Control).where(
                Control.id == control_id,
                Control.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control not found")
        return row

    @staticmethod
    def validate_status_transition(current_status: str, next_status: str) -> None:
        if current_status not in POLICY_STATUSES or next_status not in POLICY_STATUSES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid policy status")
        if current_status == next_status:
            return
        expected_next = NEXT_STATUS.get(current_status)
        if expected_next != next_status:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status transition: {current_status} -> {next_status}",
            )

    @staticmethod
    def canonical_json(payload: dict | list) -> str:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    @classmethod
    def content_sha256_hexdigest(cls, payload: dict | list) -> str:
        return hashlib.sha256(cls.canonical_json(payload).encode("utf-8")).hexdigest()

    @staticmethod
    def _diffable_text(payload: dict | list) -> str:
        """Best-effort plain-text rendering of a version's content_snapshot_json
        for line-level diffing. Every drafting/apply pipeline in this codebase
        (AI drafting apply, AI-policy-draft accept, policy-template apply) stores
        the actual document under a top-level "content" string key, so prefer
        that verbatim (real markdown/prose, diffed as-written). Snapshots without
        a string "content" key (e.g. ad-hoc structured JSON bodies) fall back to
        pretty-printed, key-sorted JSON so the diff is still deterministic and
        line-addressable rather than one giant opaque blob.
        """
        if isinstance(payload, dict):
            content = payload.get("content")
            if isinstance(content, str):
                return content
        return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)

    @staticmethod
    def _word_count(text: str) -> int:
        return len(text.split())

    @classmethod
    def diff_versions(
        cls,
        older: CompliancePolicyVersion,
        newer: CompliancePolicyVersion,
    ) -> dict:
        """Computes a real structural/line-level diff between two policy
        versions. `older`/`newer` must already be ordered chronologically by
        the caller (older.created_at <= newer.created_at).
        """
        older_text = cls._diffable_text(older.content_snapshot_json)
        newer_text = cls._diffable_text(newer.content_snapshot_json)

        older_lines = older_text.splitlines()
        newer_lines = newer_text.splitlines()

        unified = "\n".join(
            difflib.unified_diff(
                older_lines,
                newer_lines,
                fromfile=f"version {older.version_number}",
                tofile=f"version {newer.version_number}",
                lineterm="",
            )
        )

        matcher = difflib.SequenceMatcher(a=older_lines, b=newer_lines, autojunk=False)
        line_hunks = [
            {
                "op": op,
                "older_lines": older_lines[a1:a2],
                "newer_lines": newer_lines[b1:b2],
            }
            for op, a1, a2, b1, b2 in matcher.get_opcodes()
            if op != "equal" or (a2 - a1) > 0
        ]

        json_field_diffs: list[dict] = []
        older_json = older.content_snapshot_json
        newer_json = newer.content_snapshot_json
        if isinstance(older_json, dict) and isinstance(newer_json, dict):
            all_keys = sorted(set(older_json.keys()) | set(newer_json.keys()))
            for key in all_keys:
                # The "content" field is already covered in full detail by
                # unified_diff/line_hunks above; do not duplicate it here.
                if key == "content":
                    continue
                has_old = key in older_json
                has_new = key in newer_json
                old_value = older_json.get(key)
                new_value = newer_json.get(key)
                if has_old and not has_new:
                    json_field_diffs.append({"field": key, "change": "removed", "older_value": old_value, "newer_value": None})
                elif has_new and not has_old:
                    json_field_diffs.append({"field": key, "change": "added", "older_value": None, "newer_value": new_value})
                elif old_value != new_value:
                    json_field_diffs.append(
                        {"field": key, "change": "changed", "older_value": old_value, "newer_value": new_value}
                    )

        return {
            "older_text": older_text,
            "newer_text": newer_text,
            "unified_diff": unified,
            "line_hunks": line_hunks,
            "json_field_diffs": json_field_diffs,
            "identical": older_text == newer_text and older_json == newer_json,
        }

    def summary(self, organization_id: uuid.UUID) -> dict[str, int | dict[str, int]]:
        total_policies = int(
            self.db.execute(
                select(func.count(CompliancePolicy.id)).where(CompliancePolicy.organization_id == organization_id)
            ).scalar_one()
        )

        by_status_rows = self.db.execute(
            select(CompliancePolicy.status, func.count(CompliancePolicy.id))
            .where(CompliancePolicy.organization_id == organization_id)
            .group_by(CompliancePolicy.status)
        ).all()
        by_policy_type_rows = self.db.execute(
            select(CompliancePolicy.policy_type, func.count(CompliancePolicy.id))
            .where(CompliancePolicy.organization_id == organization_id)
            .group_by(CompliancePolicy.policy_type)
        ).all()

        return {
            "total_policies": total_policies,
            "by_status": {str(status_key): int(count) for status_key, count in by_status_rows},
            "by_policy_type": {str(type_key): int(count) for type_key, count in by_policy_type_rows},
        }

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def version_context(
        self,
        organization_id: uuid.UUID,
        policy: CompliancePolicy,
        versions: list[CompliancePolicyVersion],
    ) -> dict[uuid.UUID, dict[str, bool]]:
        """Per-version intelligence: which version is currently live/effective, and whether any
        still-active attestation campaign is referencing a version that is no longer live (e.g.
        it was superseded or rejected after the campaign was launched). Campaigns may reference a
        version either by FK (policy_version_id) or by the legacy version-number snapshot string,
        so both are checked.
        """
        active_campaigns = self.db.execute(
            select(PolicyAttestationCampaign.policy_version_id, PolicyAttestationCampaign.policy_version).where(
                PolicyAttestationCampaign.organization_id == organization_id,
                PolicyAttestationCampaign.policy_id == policy.id,
                PolicyAttestationCampaign.status == "active",
                PolicyAttestationCampaign.deleted_at.is_(None),
            )
        ).all()
        referenced_version_ids = {row[0] for row in active_campaigns if row[0] is not None}
        referenced_version_numbers = {row[1] for row in active_campaigns if row[1] is not None}

        context: dict[uuid.UUID, dict[str, bool]] = {}
        for version in versions:
            is_live = version.status == "approved" and version.version_number == policy.version
            referenced = version.id in referenced_version_ids or version.version_number in referenced_version_numbers
            context[version.id] = {
                "is_live": is_live,
                "referenced_by_active_campaign": referenced,
                "stale_active_campaign_reference": referenced and not is_live,
            }
        return context

    def create_policy(
        self,
        *,
        organization_id: uuid.UUID,
        title: str,
        description: str | None,
        policy_type: str,
        owner_user_id: uuid.UUID,
        policy_status: str = "draft",
        version: str = "1.0",
        content_url: str | None = None,
        tags_json: dict | list | None = None,
        notes: str | None = None,
        effective_date=None,
        review_due_date=None,
        business_unit_id: uuid.UUID | None = None,
        ai_drafted: bool = False,
        source_ai_draft_id: uuid.UUID | None = None,
    ) -> CompliancePolicy:
        # Free-plan capacity invariant (atomic, alternate-path-proof). THE enforcement
        # point for policies -- covers the direct create route AND template-apply, which
        # funnels through here and previously bypassed the per-route cap dependency.
        from app.platform.services.billing_service import BillingService

        BillingService(self.db).enforce_capacity(organization_id, "policies")

        self.ensure_owner_is_active_member(organization_id, owner_user_id)
        if policy_status != "draft":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New policies must start in draft status")

        row = CompliancePolicy(
            organization_id=organization_id,
            title=title,
            description=description,
            policy_type=policy_type,
            status=policy_status,
            owner_user_id=owner_user_id,
            effective_date=effective_date,
            review_due_date=review_due_date,
            version=version,
            content_url=content_url,
            tags_json=tags_json,
            notes=notes,
            business_unit_id=business_unit_id,
            ai_drafted=ai_drafted,
            source_ai_draft_id=source_ai_draft_id,
        )
        self.db.add(row)
        self.db.flush()
        return row
