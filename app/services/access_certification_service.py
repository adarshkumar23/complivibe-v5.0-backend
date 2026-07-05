import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.validation import validate_choice
from app.models.access_certification import AccessCertificationCampaign, AccessCertificationItem
from app.models.membership import Membership
from app.schemas.access_certification import (
    AccessCertificationCampaignCreate,
    AccessCertificationCampaignUpdate,
    AccessCertificationDecisionSubmit,
)
from app.services.audit_service import AuditService

ALLOWED_CAMPAIGN_STATUSES = {"draft", "active", "completed", "cancelled", "archived"}
ALLOWED_ITEM_STATUSES = {"pending", "certified", "revoked", "flagged"}
ALLOWED_DECISIONS = {"certified", "revoked", "flagged"}


class AccessCertificationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)

    def _audit(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        before_json: dict | None = None,
        after_json: dict | None = None,
        metadata_json: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        AuditService(self.db).write_audit_log(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            before_json=before_json,
            after_json=after_json,
            metadata_json=metadata_json or {"source": "api"},
            ip_address=ip_address,
            user_agent=user_agent,
        )

    def ensure_active_member(self, organization_id: uuid.UUID, user_id: uuid.UUID, field_name: str) -> None:
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

    def get_campaign(self, organization_id: uuid.UUID, campaign_id: uuid.UUID) -> AccessCertificationCampaign:
        row = self.db.execute(
            select(AccessCertificationCampaign).where(
                AccessCertificationCampaign.id == campaign_id,
                AccessCertificationCampaign.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access certification campaign not found")
        return row

    def get_item(self, organization_id: uuid.UUID, item_id: uuid.UUID) -> AccessCertificationItem:
        row = self.db.execute(
            select(AccessCertificationItem).where(
                AccessCertificationItem.id == item_id,
                AccessCertificationItem.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access certification item not found")
        return row

    def list_campaigns(self, organization_id: uuid.UUID, *, include_archived: bool = False) -> list[AccessCertificationCampaign]:
        stmt = select(AccessCertificationCampaign).where(AccessCertificationCampaign.organization_id == organization_id)
        if not include_archived:
            stmt = stmt.where(AccessCertificationCampaign.status != "archived")
        return list(self.db.execute(stmt.order_by(AccessCertificationCampaign.created_at.desc())).scalars().all())

    def list_items_for_campaign(self, organization_id: uuid.UUID, campaign_id: uuid.UUID) -> list[AccessCertificationItem]:
        return list(
            self.db.execute(
                select(AccessCertificationItem)
                .where(
                    AccessCertificationItem.organization_id == organization_id,
                    AccessCertificationItem.campaign_id == campaign_id,
                )
                .order_by(AccessCertificationItem.created_at.asc())
            )
            .scalars()
            .all()
        )

    def list_my_certifications(
        self,
        organization_id: uuid.UUID,
        reviewer_user_id: uuid.UUID,
        *,
        status_filter: str | None = None,
    ) -> list[AccessCertificationItem]:
        stmt = select(AccessCertificationItem).where(
            AccessCertificationItem.organization_id == organization_id,
            AccessCertificationItem.reviewer_user_id == reviewer_user_id,
        )
        if status_filter is not None:
            validate_choice(status_filter, ALLOWED_ITEM_STATUSES, "status", status_code=status.HTTP_400_BAD_REQUEST)
            stmt = stmt.where(AccessCertificationItem.status == status_filter)
        return list(self.db.execute(stmt.order_by(AccessCertificationItem.created_at.desc())).scalars().all())

    def campaign_counts(self, organization_id: uuid.UUID, campaign_id: uuid.UUID) -> dict[str, int]:
        rows = self.db.execute(
            select(AccessCertificationItem.status, func.count(AccessCertificationItem.id))
            .where(
                AccessCertificationItem.organization_id == organization_id,
                AccessCertificationItem.campaign_id == campaign_id,
            )
            .group_by(AccessCertificationItem.status)
        ).all()
        counts = {status_value: int(count) for status_value, count in rows}
        return {
            "total_items": sum(counts.values()),
            "pending_items": counts.get("pending", 0),
            "certified_items": counts.get("certified", 0),
            "revoked_items": counts.get("revoked", 0),
            "flagged_items": counts.get("flagged", 0),
        }

    def create_campaign(
        self,
        *,
        organization_id: uuid.UUID,
        payload: AccessCertificationCampaignCreate,
        actor_user_id: uuid.UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AccessCertificationCampaign:
        validate_choice(payload.status, ALLOWED_CAMPAIGN_STATUSES, "status", status_code=status.HTTP_400_BAD_REQUEST)
        for item in payload.items:
            self.ensure_active_member(organization_id, item.user_id, "user_id")
            self.ensure_active_member(organization_id, item.reviewer_user_id, "reviewer_user_id")

        now = self.now()
        row = AccessCertificationCampaign(
            organization_id=organization_id,
            name=payload.name,
            description=payload.description,
            scope_type=payload.scope_type,
            scope_config_json=payload.scope_config_json,
            status=payload.status,
            due_date=payload.due_date,
            launched_at=now if payload.status == "active" else None,
            completed_at=now if payload.status == "completed" else None,
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()

        self._audit(
            action="access_certification_campaign.created",
            entity_type="access_certification_campaign",
            entity_id=row.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            after_json={"name": row.name, "status": row.status, "scope_type": row.scope_type},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        for item_payload in payload.items:
            item = AccessCertificationItem(
                organization_id=organization_id,
                campaign_id=row.id,
                user_id=item_payload.user_id,
                reviewer_user_id=item_payload.reviewer_user_id,
                system_key=item_payload.system_key,
                system_name=item_payload.system_name,
                access_level=item_payload.access_level,
                status="pending",
                metadata_json=item_payload.metadata_json,
            )
            self.db.add(item)
            self.db.flush()
            self._audit(
                action="access_certification_item.created",
                entity_type="access_certification_item",
                entity_id=item.id,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                after_json={
                    "campaign_id": str(row.id),
                    "user_id": str(item.user_id),
                    "reviewer_user_id": str(item.reviewer_user_id),
                    "system_key": item.system_key,
                    "status": item.status,
                },
                ip_address=ip_address,
                user_agent=user_agent,
            )

        return row

    def update_campaign(
        self,
        *,
        campaign: AccessCertificationCampaign,
        payload: AccessCertificationCampaignUpdate,
        actor_user_id: uuid.UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AccessCertificationCampaign:
        before = {
            "name": campaign.name,
            "description": campaign.description,
            "scope_type": campaign.scope_type,
            "scope_config_json": campaign.scope_config_json,
            "due_date": campaign.due_date.isoformat() if campaign.due_date else None,
            "status": campaign.status,
        }
        updates = payload.model_dump(exclude_unset=True)
        if "status" in updates and updates["status"] is not None:
            validate_choice(updates["status"], ALLOWED_CAMPAIGN_STATUSES, "status", status_code=status.HTTP_400_BAD_REQUEST)

        for field, value in updates.items():
            setattr(campaign, field, value)

        now = self.now()
        if before["status"] != "active" and campaign.status == "active" and campaign.launched_at is None:
            campaign.launched_at = now
        if before["status"] != "completed" and campaign.status == "completed" and campaign.completed_at is None:
            campaign.completed_at = now

        self.db.flush()
        self._audit(
            action="access_certification_campaign.updated",
            entity_type="access_certification_campaign",
            entity_id=campaign.id,
            organization_id=campaign.organization_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json={
                "name": campaign.name,
                "description": campaign.description,
                "scope_type": campaign.scope_type,
                "scope_config_json": campaign.scope_config_json,
                "due_date": campaign.due_date.isoformat() if campaign.due_date else None,
                "status": campaign.status,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return campaign

    def archive_campaign(
        self,
        *,
        campaign: AccessCertificationCampaign,
        actor_user_id: uuid.UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AccessCertificationCampaign:
        before_status = campaign.status
        campaign.status = "archived"
        self.db.flush()
        self._audit(
            action="access_certification_campaign.archived",
            entity_type="access_certification_campaign",
            entity_id=campaign.id,
            organization_id=campaign.organization_id,
            actor_user_id=actor_user_id,
            before_json={"status": before_status},
            after_json={"status": campaign.status},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return campaign

    def submit_decision(
        self,
        *,
        item: AccessCertificationItem,
        campaign: AccessCertificationCampaign,
        payload: AccessCertificationDecisionSubmit,
        actor_user_id: uuid.UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AccessCertificationItem:
        decision = validate_choice(payload.decision, ALLOWED_DECISIONS, "decision", status_code=status.HTTP_400_BAD_REQUEST)
        if campaign.status in {"cancelled", "archived"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Campaign is not open for decisions")
        if item.reviewer_user_id != actor_user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the assigned reviewer can submit this decision")

        before = {"status": item.status, "decision": item.decision, "decision_comment": item.decision_comment}
        item.status = decision
        item.decision = decision
        item.decision_comment = payload.comment
        item.decided_by_user_id = actor_user_id
        item.decided_at = self.now()
        self.db.flush()

        self._audit(
            action="access_certification_item.decision_submitted",
            entity_type="access_certification_item",
            entity_id=item.id,
            organization_id=item.organization_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json={"status": item.status, "decision": item.decision, "decision_comment": item.decision_comment},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        counts = self.campaign_counts(campaign.organization_id, campaign.id)
        if counts["total_items"] > 0 and counts["pending_items"] == 0 and campaign.status != "completed":
            before_campaign_status = campaign.status
            campaign.status = "completed"
            campaign.completed_at = self.now()
            self.db.flush()
            self._audit(
                action="access_certification_campaign.completed",
                entity_type="access_certification_campaign",
                entity_id=campaign.id,
                organization_id=campaign.organization_id,
                actor_user_id=actor_user_id,
                before_json={"status": before_campaign_status},
                after_json={"status": campaign.status},
                ip_address=ip_address,
                user_agent=user_agent,
            )

        return item
