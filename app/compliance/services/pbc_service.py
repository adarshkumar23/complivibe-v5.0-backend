import uuid
from datetime import UTC, date, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.compliance.services.audit_engagement_service import AuditEngagementService
from app.models.evidence_item import EvidenceItem
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.pbc_item import PbcItem
from app.models.user import User
from app.schemas.pbc_item import PbcItemCreate, PbcItemUpdate
from app.services.audit_service import AuditService


class PbcService:
    ALLOWED_TRANSITIONS: dict[str, set[str]] = {
        "pending": {"submitted", "overdue", "rejected"},
        "submitted": {"accepted", "rejected"},
        "accepted": set(),
        "rejected": {"pending"},
        "overdue": {"submitted"},
    }

    def __init__(self, db: Session) -> None:
        self.db = db
        self.engagement_service = AuditEngagementService(db)

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def utcdate() -> date:
        return datetime.now(UTC).date()

    def require_pbc_item(self, org_id: uuid.UUID, item_id: uuid.UUID) -> PbcItem:
        row = self.db.execute(
            select(PbcItem).where(
                PbcItem.organization_id == org_id,
                PbcItem.id == item_id,
                PbcItem.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PBC item not found")
        return row

    def _validate_assignee(self, org_id: uuid.UUID, assignee_id: uuid.UUID | None) -> None:
        if assignee_id is None:
            return
        member = self.db.execute(
            select(Membership)
            .join(User, User.id == Membership.user_id)
            .where(
                Membership.organization_id == org_id,
                Membership.user_id == assignee_id,
                Membership.status == "active",
                User.is_active.is_(True),
                User.status == "active",
            )
        ).scalar_one_or_none()
        if member is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="assignee_id must be an active organization member",
            )

    def _validate_evidence(self, org_id: uuid.UUID, evidence_id: uuid.UUID) -> EvidenceItem:
        row = self.db.execute(
            select(EvidenceItem).where(
                EvidenceItem.organization_id == org_id,
                EvidenceItem.id == evidence_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="evidence_id must belong to the same organization",
            )
        return row

    def _transition(self, row: PbcItem, new_status: str) -> None:
        allowed = self.ALLOWED_TRANSITIONS.get(row.status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status transition from {row.status} to {new_status}",
            )

    def create_pbc_item(
        self,
        org_id: uuid.UUID,
        engagement_id: uuid.UUID,
        data: PbcItemCreate,
        requester_id: uuid.UUID,
    ) -> PbcItem:
        self.engagement_service.require_engagement(org_id, engagement_id)
        self._validate_assignee(org_id, data.assignee_id)

        row = PbcItem(
            organization_id=org_id,
            audit_engagement_id=engagement_id,
            title=data.title,
            description=data.description,
            requester_id=requester_id,
            assignee_id=data.assignee_id,
            due_date=data.due_date,
            status="pending",
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="pbc_item.created",
            entity_type="pbc_item",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=requester_id,
            after_json={
                "audit_engagement_id": str(row.audit_engagement_id),
                "status": row.status,
                "due_date": str(row.due_date),
                "assignee_id": str(row.assignee_id) if row.assignee_id else None,
            },
            metadata_json={"source": "api"},
        )
        return row

    def get_pbc_item(self, org_id: uuid.UUID, item_id: uuid.UUID) -> PbcItem:
        return self.require_pbc_item(org_id, item_id)

    def list_pbc_items(
        self,
        org_id: uuid.UUID,
        *,
        engagement_id: uuid.UUID | None = None,
        assignee_id: uuid.UUID | None = None,
        status_value: str | None = None,
        overdue_only: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> list[PbcItem]:
        if engagement_id is not None:
            self.engagement_service.require_engagement(org_id, engagement_id)

        stmt = select(PbcItem).where(
            PbcItem.organization_id == org_id,
            PbcItem.deleted_at.is_(None),
        )
        if engagement_id is not None:
            stmt = stmt.where(PbcItem.audit_engagement_id == engagement_id)
        if assignee_id is not None:
            stmt = stmt.where(PbcItem.assignee_id == assignee_id)
        if status_value is not None:
            stmt = stmt.where(PbcItem.status == status_value)

        if overdue_only:
            stmt = stmt.where(
                PbcItem.due_date < self.utcdate(),
                PbcItem.status.in_(["pending", "overdue"]),
            )

        rows = self.db.execute(stmt.order_by(PbcItem.due_date.asc(), PbcItem.created_at.desc())).scalars().all()
        return rows[skip : skip + limit]

    def update_pbc_item(self, org_id: uuid.UUID, item_id: uuid.UUID, data: PbcItemUpdate) -> PbcItem:
        row = self.require_pbc_item(org_id, item_id)
        updates = data.model_dump(exclude_unset=True)

        if "assignee_id" in updates:
            self._validate_assignee(org_id, updates["assignee_id"])

        for key, value in updates.items():
            setattr(row, key, value)
        self.db.flush()
        return row

    def submit_pbc_item(
        self,
        org_id: uuid.UUID,
        item_id: uuid.UUID,
        user_id: uuid.UUID,
        evidence_id: uuid.UUID | None = None,
    ) -> PbcItem:
        row = self.require_pbc_item(org_id, item_id)
        if row.assignee_id is not None and user_id != row.assignee_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only assignee can submit this PBC item")
        if row.assignee_id is None and user_id != row.requester_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to submit this PBC item")

        self._transition(row, "submitted")

        if evidence_id is not None:
            self._validate_evidence(org_id, evidence_id)
            row.evidence_id = evidence_id

        row.status = "submitted"
        row.submitted_at = self.utcnow()
        row.accepted_at = None
        row.rejected_at = None
        row.rejection_reason = None
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="pbc_item.submitted",
            entity_type="pbc_item",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={
                "status": row.status,
                "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
                "evidence_id": str(row.evidence_id) if row.evidence_id else None,
            },
            metadata_json={"source": "api"},
        )
        return row

    def accept_pbc_item(
        self,
        org_id: uuid.UUID,
        item_id: uuid.UUID,
        user_id: uuid.UUID,
        override_reason: str | None = None,
    ) -> PbcItem:
        row = self.require_pbc_item(org_id, item_id)
        if row.requester_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only requester can accept this PBC item")

        self._transition(row, "accepted")

        # A PBC item with no evidence attached is missing the client's proof of
        # compliance. Accepting it silently would defeat the point of the PBC
        # workflow, so acceptance requires either evidence being on file or an
        # explicit, recorded override reason documenting why it's being waived.
        override_reason = override_reason.strip() if override_reason else None
        if row.evidence_id is None and not override_reason:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Cannot accept a PBC item with no evidence attached. Attach evidence via "
                    "/submit, or supply override_reason to explicitly document why acceptance "
                    "is proceeding without it."
                ),
            )

        row.status = "accepted"
        row.accepted_at = self.utcnow()
        row.acceptance_override_reason = override_reason
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="pbc_item.accepted",
            entity_type="pbc_item",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={
                "status": row.status,
                "accepted_at": row.accepted_at.isoformat() if row.accepted_at else None,
                "evidence_id": str(row.evidence_id) if row.evidence_id else None,
                "acceptance_override_reason": row.acceptance_override_reason,
            },
            metadata_json={"source": "api", "accepted_without_evidence": row.evidence_id is None},
        )
        return row

    def reject_pbc_item(
        self,
        org_id: uuid.UUID,
        item_id: uuid.UUID,
        user_id: uuid.UUID,
        rejection_reason: str,
    ) -> PbcItem:
        row = self.require_pbc_item(org_id, item_id)
        if row.requester_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only requester can reject this PBC item")

        self._transition(row, "rejected")
        row.status = "rejected"
        row.rejected_at = self.utcnow()
        row.rejection_reason = rejection_reason
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="pbc_item.rejected",
            entity_type="pbc_item",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={
                "status": row.status,
                "rejected_at": row.rejected_at.isoformat() if row.rejected_at else None,
                "rejection_reason": row.rejection_reason,
            },
            metadata_json={"source": "api"},
        )
        return row

    def mark_overdue_items(self, org_id: uuid.UUID) -> int:
        today = self.utcdate()
        rows = self.db.execute(
            select(PbcItem).where(
                PbcItem.organization_id == org_id,
                PbcItem.deleted_at.is_(None),
                PbcItem.status == "pending",
                PbcItem.due_date < today,
            )
        ).scalars().all()

        for row in rows:
            row.status = "overdue"
            AuditService(self.db).write_audit_log(
                action="pbc_item.overdue_marked",
                entity_type="pbc_item",
                entity_id=row.id,
                organization_id=org_id,
                after_json={"status": row.status, "due_date": str(row.due_date)},
                metadata_json={"source": "scheduler"},
            )

        self.db.flush()
        return len(rows)

    def get_pbc_summary(self, org_id: uuid.UUID, engagement_id: uuid.UUID | None = None) -> dict:
        if engagement_id is not None:
            self.engagement_service.require_engagement(org_id, engagement_id)

        stmt = select(PbcItem).where(PbcItem.organization_id == org_id, PbcItem.deleted_at.is_(None))
        if engagement_id is not None:
            stmt = stmt.where(PbcItem.audit_engagement_id == engagement_id)

        rows = self.db.execute(stmt).scalars().all()
        total_items = len(rows)

        by_status: dict[str, int] = {key: 0 for key in ["pending", "submitted", "accepted", "rejected", "overdue"]}
        overdue_count = 0
        items_without_evidence = 0
        submit_durations: list[float] = []
        today = self.utcdate()

        for row in rows:
            by_status[row.status] = by_status.get(row.status, 0) + 1
            if row.status in {"pending", "overdue"} and row.due_date < today:
                overdue_count += 1
            if row.evidence_id is None:
                items_without_evidence += 1
            if row.status in {"submitted", "accepted"} and row.submitted_at is not None:
                delta = row.submitted_at - row.created_at
                submit_durations.append(delta.total_seconds() / 86400)

        completion_rate = round((by_status.get("accepted", 0) / total_items) * 100, 2) if total_items else 0.0
        avg_days_to_submit = round(sum(submit_durations) / len(submit_durations), 2) if submit_durations else None

        return {
            "total_items": total_items,
            "by_status": by_status,
            "overdue_count": overdue_count,
            "completion_rate": completion_rate,
            "items_without_evidence": items_without_evidence,
            "avg_days_to_submit": avg_days_to_submit,
        }

    def soft_delete_pbc_item(self, org_id: uuid.UUID, item_id: uuid.UUID, user_id: uuid.UUID) -> PbcItem:
        row = self.require_pbc_item(org_id, item_id)
        if row.status not in {"pending", "rejected"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Only pending or rejected PBC items can be deleted",
            )

        row.deleted_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="pbc_item.deleted",
            entity_type="pbc_item",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"deleted_at": row.deleted_at.isoformat() if row.deleted_at else None, "status": row.status},
            metadata_json={"source": "api"},
        )
        return row


def run_daily_pbc_overdue_sweep(db: Session) -> int:
    org_ids = [row[0] for row in db.execute(select(Organization.id)).all()]
    total_marked = 0
    service = PbcService(db)
    for org_id in org_ids:
        total_marked += service.mark_overdue_items(org_id)
    return total_marked
