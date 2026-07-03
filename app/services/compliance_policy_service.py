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
