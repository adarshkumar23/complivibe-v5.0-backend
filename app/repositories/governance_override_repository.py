import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.governance_override_approval import GovernanceOverrideApproval
from app.models.governance_override_event import GovernanceOverrideEvent
from app.models.governance_override_request import GovernanceOverrideRequest
from app.models.governance_override_template import GovernanceOverrideTemplate
from app.models.governance_override_template_version import GovernanceOverrideTemplateVersion


class GovernanceOverrideRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_request(self, override_id: uuid.UUID) -> GovernanceOverrideRequest | None:
        return self.db.execute(select(GovernanceOverrideRequest).where(GovernanceOverrideRequest.id == override_id)).scalar_one_or_none()

    def list_requests(
        self,
        *,
        organization_id: uuid.UUID,
        status: str | None,
        override_type: str | None,
        target_entity_type: str | None,
        requested_action: str | None,
        limit: int,
        offset: int,
    ) -> list[GovernanceOverrideRequest]:
        stmt = select(GovernanceOverrideRequest).where(GovernanceOverrideRequest.organization_id == organization_id)
        if status:
            stmt = stmt.where(GovernanceOverrideRequest.status == status)
        if override_type:
            stmt = stmt.where(GovernanceOverrideRequest.override_type == override_type)
        if target_entity_type:
            stmt = stmt.where(GovernanceOverrideRequest.target_entity_type == target_entity_type)
        if requested_action:
            stmt = stmt.where(GovernanceOverrideRequest.requested_action == requested_action)
        stmt = stmt.order_by(GovernanceOverrideRequest.created_at.desc()).offset(offset).limit(limit)
        return self.db.execute(stmt).scalars().all()

    def list_approvals(self, *, organization_id: uuid.UUID, override_request_id: uuid.UUID) -> list[GovernanceOverrideApproval]:
        stmt = (
            select(GovernanceOverrideApproval)
            .where(
                GovernanceOverrideApproval.organization_id == organization_id,
                GovernanceOverrideApproval.override_request_id == override_request_id,
            )
            .order_by(GovernanceOverrideApproval.created_at.asc())
        )
        return self.db.execute(stmt).scalars().all()

    def list_events(self, *, organization_id: uuid.UUID, override_request_id: uuid.UUID) -> list[GovernanceOverrideEvent]:
        stmt = (
            select(GovernanceOverrideEvent)
            .where(
                GovernanceOverrideEvent.organization_id == organization_id,
                GovernanceOverrideEvent.override_request_id == override_request_id,
            )
            .order_by(GovernanceOverrideEvent.created_at.asc())
        )
        return self.db.execute(stmt).scalars().all()

    def get_approval_by_user(
        self,
        *,
        organization_id: uuid.UUID,
        override_request_id: uuid.UUID,
        approver_user_id: uuid.UUID,
    ) -> GovernanceOverrideApproval | None:
        stmt = select(GovernanceOverrideApproval).where(
            GovernanceOverrideApproval.organization_id == organization_id,
            GovernanceOverrideApproval.override_request_id == override_request_id,
            GovernanceOverrideApproval.approver_user_id == approver_user_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_template(self, template_id: uuid.UUID) -> GovernanceOverrideTemplate | None:
        return self.db.execute(select(GovernanceOverrideTemplate).where(GovernanceOverrideTemplate.id == template_id)).scalar_one_or_none()

    def list_templates(
        self,
        *,
        organization_id: uuid.UUID,
        status: str | None,
        override_type: str | None,
        target_entity_type: str | None,
        requested_action: str | None,
        limit: int,
        offset: int,
    ) -> list[GovernanceOverrideTemplate]:
        stmt = select(GovernanceOverrideTemplate).where(GovernanceOverrideTemplate.organization_id == organization_id)
        if status:
            stmt = stmt.where(GovernanceOverrideTemplate.status == status)
        if override_type:
            stmt = stmt.where(GovernanceOverrideTemplate.override_type == override_type)
        if target_entity_type:
            stmt = stmt.where(GovernanceOverrideTemplate.target_entity_type == target_entity_type)
        if requested_action:
            stmt = stmt.where(GovernanceOverrideTemplate.requested_action == requested_action)
        stmt = stmt.order_by(GovernanceOverrideTemplate.created_at.desc()).offset(offset).limit(limit)
        return self.db.execute(stmt).scalars().all()

    def list_template_versions(self, *, organization_id: uuid.UUID, template_id: uuid.UUID) -> list[GovernanceOverrideTemplateVersion]:
        stmt = (
            select(GovernanceOverrideTemplateVersion)
            .where(
                GovernanceOverrideTemplateVersion.organization_id == organization_id,
                GovernanceOverrideTemplateVersion.template_id == template_id,
            )
            .order_by(GovernanceOverrideTemplateVersion.version.desc(), GovernanceOverrideTemplateVersion.created_at.desc())
        )
        return self.db.execute(stmt).scalars().all()

    def count_template_bound_requests_since(self, *, organization_id: uuid.UUID, since) -> int:
        return int(
            self.db.execute(
                select(func.count(GovernanceOverrideRequest.id)).where(
                    GovernanceOverrideRequest.organization_id == organization_id,
                    GovernanceOverrideRequest.template_id.is_not(None),
                    GovernanceOverrideRequest.created_at >= since,
                )
            ).scalar_one()
        )
