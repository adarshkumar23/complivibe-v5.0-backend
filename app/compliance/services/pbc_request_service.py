import uuid
from datetime import UTC, date, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.services.audit_engagement_service import AuditEngagementService
from app.models.evidence_item import EvidenceItem
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.pbc_request import PBCRequest
from app.models.user import User
from app.services.audit_service import AuditService


class PBCRequestService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.engagement_service = AuditEngagementService(db)

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def utcdate() -> date:
        return datetime.now(UTC).date()

    def require_request(self, org_id: uuid.UUID, request_id: uuid.UUID) -> PBCRequest:
        row = self.db.execute(
            select(PBCRequest).where(
                PBCRequest.organization_id == org_id,
                PBCRequest.id == request_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PBC request not found")
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
                detail="assigned_to must be an active organization member",
            )

    def _validate_evidence(self, org_id: uuid.UUID, evidence_id: uuid.UUID | None) -> None:
        if evidence_id is None:
            return
        row = self.db.execute(
            select(EvidenceItem.id).where(
                EvidenceItem.organization_id == org_id,
                EvidenceItem.id == evidence_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")

    def bulk_create(
        self,
        org_id: uuid.UUID,
        audit_id: uuid.UUID,
        items: list[dict],
        created_by: uuid.UUID,
    ) -> list[PBCRequest]:
        self.engagement_service.require_engagement(org_id, audit_id)
        rows: list[PBCRequest] = []
        for item in items:
            assigned_to = item.get("assigned_to")
            self._validate_assignee(org_id, assigned_to)
            row = PBCRequest(
                organization_id=org_id,
                audit_id=audit_id,
                item_description=item["item_description"],
                assigned_to=assigned_to,
                due_date=item.get("due_date"),
                status="open",
                created_by=created_by,
            )
            self.db.add(row)
            rows.append(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="pbc.requests_bulk_created",
            entity_type="pbc_request",
            organization_id=org_id,
            actor_user_id=created_by,
            metadata_json={"audit_id": str(audit_id), "count": len(rows)},
        )
        return rows

    def submit(
        self,
        org_id: uuid.UUID,
        request_id: uuid.UUID,
        submitted_by: uuid.UUID,
        evidence_id: uuid.UUID | None = None,
    ) -> PBCRequest:
        row = self.require_request(org_id, request_id)
        if row.status in {"submitted", "accepted"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="PBC request already submitted/accepted")
        self._validate_evidence(org_id, evidence_id)
        row.status = "submitted"
        row.submitted_at = self.utcnow()
        if evidence_id is not None:
            row.evidence_id = evidence_id
        row.accepted_at = None
        row.rejected_at = None
        row.rejection_reason = None
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="pbc.request_submitted",
            entity_type="pbc_request",
            organization_id=org_id,
            actor_user_id=submitted_by,
            entity_id=row.id,
            metadata_json={"evidence_id": str(row.evidence_id) if row.evidence_id else None},
        )
        return row

    def accept(self, org_id: uuid.UUID, request_id: uuid.UUID, accepted_by: uuid.UUID) -> PBCRequest:
        row = self.require_request(org_id, request_id)
        if row.status != "submitted":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only submitted PBC requests can be accepted")
        row.status = "accepted"
        row.accepted_at = self.utcnow()
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="pbc.request_accepted",
            entity_type="pbc_request",
            organization_id=org_id,
            actor_user_id=accepted_by,
            entity_id=row.id,
        )
        return row

    def reject(
        self,
        org_id: uuid.UUID,
        request_id: uuid.UUID,
        rejected_by: uuid.UUID,
        rejection_reason: str | None = None,
    ) -> PBCRequest:
        row = self.require_request(org_id, request_id)
        if row.status != "submitted":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only submitted PBC requests can be rejected")
        row.status = "rejected"
        row.rejected_at = self.utcnow()
        row.rejection_reason = rejection_reason
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="pbc.request_rejected",
            entity_type="pbc_request",
            organization_id=org_id,
            actor_user_id=rejected_by,
            entity_id=row.id,
            metadata_json={"rejection_reason": rejection_reason},
        )
        return row

    def mark_overdue(self, org_id: uuid.UUID | None = None) -> int:
        stmt = select(PBCRequest).where(
            PBCRequest.status == "open",
            PBCRequest.due_date.is_not(None),
            PBCRequest.due_date < self.utcdate(),
        )
        if org_id is not None:
            stmt = stmt.where(PBCRequest.organization_id == org_id)
        rows = self.db.execute(stmt).scalars().all()
        for row in rows:
            row.status = "overdue"
            AuditService(self.db).write_audit_log(
                action="pbc.request_overdue",
                entity_type="pbc_request",
                organization_id=row.organization_id,
                entity_id=row.id,
                metadata_json={"due_date": str(row.due_date) if row.due_date else None},
            )
        self.db.flush()
        return len(rows)

    def list_requests(
        self,
        org_id: uuid.UUID,
        audit_id: uuid.UUID | None = None,
        status_value: str | None = None,
        assigned_to: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[PBCRequest]:
        stmt = select(PBCRequest).where(PBCRequest.organization_id == org_id)
        if audit_id is not None:
            stmt = stmt.where(PBCRequest.audit_id == audit_id)
        if status_value is not None:
            stmt = stmt.where(PBCRequest.status == status_value)
        if assigned_to is not None:
            stmt = stmt.where(PBCRequest.assigned_to == assigned_to)
        rows = self.db.execute(stmt.order_by(PBCRequest.created_at.desc())).scalars().all()
        start = max((page - 1) * page_size, 0)
        end = start + page_size
        return rows[start:end]


def run_daily_pbc_request_overdue_sweep(db: Session) -> int:
    org_ids = [row[0] for row in db.execute(select(Organization.id)).all()]
    total = 0
    service = PBCRequestService(db)
    for org_id in org_ids:
        total += service.mark_overdue(org_id)
    return total
