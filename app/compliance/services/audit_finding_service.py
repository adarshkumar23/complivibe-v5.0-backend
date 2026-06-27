import uuid
from datetime import UTC, date, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.compliance.services.audit_engagement_service import AuditEngagementService
from app.models.audit_finding import AuditFinding
from app.models.control import Control
from app.models.membership import Membership
from app.models.risk import Risk
from app.models.user import User
from app.schemas.audit_finding import AuditFindingCreate, AuditFindingUpdate
from app.services.audit_service import AuditService


class AuditFindingService:
    ALLOWED_TRANSITIONS: dict[str, set[str]] = {
        "open": {"in_remediation", "risk_accepted", "closed"},
        "in_remediation": {"remediated", "open"},
        "remediated": {"closed", "open"},
        "closed": set(),
        "risk_accepted": set(),
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

    def require_finding(self, org_id: uuid.UUID, finding_id: uuid.UUID) -> AuditFinding:
        row = self.db.execute(
            select(AuditFinding).where(
                AuditFinding.organization_id == org_id,
                AuditFinding.id == finding_id,
                AuditFinding.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit finding not found")
        return row

    def _validate_owner(self, org_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        member = self.db.execute(
            select(Membership)
            .join(User, User.id == Membership.user_id)
            .where(
                Membership.organization_id == org_id,
                Membership.user_id == owner_id,
                Membership.status == "active",
                User.is_active.is_(True),
                User.status == "active",
            )
        ).scalar_one_or_none()
        if member is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="assigned_owner_id must be an active organization member",
            )

    def _validate_risk(self, org_id: uuid.UUID, risk_id: uuid.UUID | None) -> None:
        if risk_id is None:
            return
        risk = self.db.execute(
            select(Risk.id).where(
                Risk.organization_id == org_id,
                Risk.id == risk_id,
            )
        ).scalar_one_or_none()
        if risk is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="risk_id must belong to same organization")

    def _validate_control(self, org_id: uuid.UUID, control_id: uuid.UUID | None) -> None:
        if control_id is None:
            return
        control = self.db.execute(
            select(Control.id).where(
                Control.organization_id == org_id,
                Control.id == control_id,
            )
        ).scalar_one_or_none()
        if control is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="control_id must belong to same organization")

    def _next_finding_ref(self, org_id: uuid.UUID, year: int, sequence: int | None = None) -> str:
        if sequence is None:
            like_prefix = f"F-{year}-%"
            count = int(
                self.db.execute(
                    select(func.count(AuditFinding.id)).where(
                        AuditFinding.organization_id == org_id,
                        AuditFinding.finding_ref.like(like_prefix),
                    )
                ).scalar_one()
            )
            sequence = count + 1
        return f"F-{year}-{sequence:03d}"

    def create_finding(
        self,
        org_id: uuid.UUID,
        engagement_id: uuid.UUID,
        data: AuditFindingCreate,
        created_by: uuid.UUID,
    ) -> AuditFinding:
        self.engagement_service.require_engagement(org_id, engagement_id)
        self._validate_owner(org_id, data.assigned_owner_id)
        self._validate_risk(org_id, data.risk_register_entry_id)
        self._validate_control(org_id, data.control_id)

        year = self.utcnow().year
        base_ref = self._next_finding_ref(org_id, year)
        base_sequence = int(base_ref.rsplit("-", 1)[1])

        for attempt in range(2):
            finding_ref = self._next_finding_ref(org_id, year, base_sequence + attempt)
            row = AuditFinding(
                organization_id=org_id,
                audit_engagement_id=engagement_id,
                finding_ref=finding_ref,
                severity=data.severity,
                framework_ref=data.framework_ref,
                title=data.title,
                description=data.description,
                assigned_owner_id=data.assigned_owner_id,
                remediation_action=data.remediation_action,
                target_remediation_date=data.target_remediation_date,
                status="open",
                risk_register_entry_id=data.risk_register_entry_id,
                control_id=data.control_id,
                closed_at=None,
                closed_by=None,
            )
            self.db.add(row)
            try:
                self.db.flush()
                AuditService(self.db).write_audit_log(
                    action="audit_finding.created",
                    entity_type="audit_finding",
                    entity_id=row.id,
                    organization_id=org_id,
                    actor_user_id=created_by,
                    after_json={
                        "finding_ref": row.finding_ref,
                        "status": row.status,
                        "severity": row.severity,
                    },
                    metadata_json={"source": "api"},
                )
                return row
            except IntegrityError:
                self.db.rollback()
                if attempt == 1:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Unable to generate unique finding_ref")

        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Unable to generate unique finding_ref")

    def get_finding(self, org_id: uuid.UUID, finding_id: uuid.UUID) -> AuditFinding:
        return self.require_finding(org_id, finding_id)

    def list_findings(
        self,
        org_id: uuid.UUID,
        *,
        engagement_id: uuid.UUID | None = None,
        severity: str | None = None,
        status_value: str | None = None,
        assigned_owner_id: uuid.UUID | None = None,
        framework_ref: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[AuditFinding]:
        stmt = select(AuditFinding).where(
            AuditFinding.organization_id == org_id,
            AuditFinding.deleted_at.is_(None),
        )
        if engagement_id is not None:
            stmt = stmt.where(AuditFinding.audit_engagement_id == engagement_id)
        if severity is not None:
            stmt = stmt.where(AuditFinding.severity == severity)
        if status_value is not None:
            stmt = stmt.where(AuditFinding.status == status_value)
        if assigned_owner_id is not None:
            stmt = stmt.where(AuditFinding.assigned_owner_id == assigned_owner_id)
        if framework_ref is not None:
            stmt = stmt.where(AuditFinding.framework_ref == framework_ref)

        rows = self.db.execute(stmt.order_by(AuditFinding.created_at.desc())).scalars().all()
        return rows[skip : skip + limit]

    def update_finding(self, org_id: uuid.UUID, finding_id: uuid.UUID, data: AuditFindingUpdate) -> AuditFinding:
        row = self.require_finding(org_id, finding_id)
        updates = data.model_dump(exclude_unset=True)

        if "assigned_owner_id" in updates and updates["assigned_owner_id"] is not None:
            self._validate_owner(org_id, updates["assigned_owner_id"])
        if "risk_register_entry_id" in updates:
            self._validate_risk(org_id, updates["risk_register_entry_id"])
        if "control_id" in updates:
            self._validate_control(org_id, updates["control_id"])

        before = {
            "severity": row.severity,
            "framework_ref": row.framework_ref,
            "title": row.title,
            "description": row.description,
            "assigned_owner_id": str(row.assigned_owner_id),
            "remediation_action": row.remediation_action,
            "target_remediation_date": str(row.target_remediation_date),
            "risk_register_entry_id": str(row.risk_register_entry_id) if row.risk_register_entry_id else None,
            "control_id": str(row.control_id) if row.control_id else None,
        }

        for key, value in updates.items():
            setattr(row, key, value)

        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="audit_finding.updated",
            entity_type="audit_finding",
            entity_id=row.id,
            organization_id=org_id,
            before_json=before,
            after_json={
                "severity": row.severity,
                "framework_ref": row.framework_ref,
                "title": row.title,
                "description": row.description,
                "assigned_owner_id": str(row.assigned_owner_id),
                "remediation_action": row.remediation_action,
                "target_remediation_date": str(row.target_remediation_date),
                "risk_register_entry_id": str(row.risk_register_entry_id) if row.risk_register_entry_id else None,
                "control_id": str(row.control_id) if row.control_id else None,
            },
            metadata_json={"source": "api"},
        )
        return row

    def transition_status(
        self,
        org_id: uuid.UUID,
        finding_id: uuid.UUID,
        new_status: str,
        user_id: uuid.UUID,
    ) -> AuditFinding:
        row = self.require_finding(org_id, finding_id)
        allowed = self.ALLOWED_TRANSITIONS.get(row.status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status transition from {row.status} to {new_status}",
            )

        before_status = row.status
        row.status = new_status
        if new_status in {"closed", "risk_accepted"}:
            row.closed_at = self.utcnow()
            row.closed_by = user_id
        else:
            row.closed_at = None
            row.closed_by = None

        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="audit_finding.status_transitioned",
            entity_type="audit_finding",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            before_json={"status": before_status},
            after_json={
                "status": row.status,
                "closed_at": row.closed_at.isoformat() if row.closed_at else None,
                "closed_by": str(row.closed_by) if row.closed_by else None,
            },
            metadata_json={"source": "api"},
        )
        return row

    def link_to_risk(self, org_id: uuid.UUID, finding_id: uuid.UUID, risk_id: uuid.UUID, user_id: uuid.UUID) -> AuditFinding:
        row = self.require_finding(org_id, finding_id)
        self._validate_risk(org_id, risk_id)
        before_risk = row.risk_register_entry_id
        row.risk_register_entry_id = risk_id
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="audit_finding.risk_linked",
            entity_type="audit_finding",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            before_json={"risk_register_entry_id": str(before_risk) if before_risk else None},
            after_json={"risk_register_entry_id": str(row.risk_register_entry_id)},
            metadata_json={"source": "api"},
        )
        return row

    def bulk_transition(
        self,
        org_id: uuid.UUID,
        finding_ids: list[uuid.UUID],
        new_status: str,
        user_id: uuid.UUID,
    ) -> dict:
        updated_count = 0
        failed_ids: list[uuid.UUID] = []

        for finding_id in finding_ids:
            row = self.db.execute(
                select(AuditFinding).where(
                    AuditFinding.organization_id == org_id,
                    AuditFinding.id == finding_id,
                    AuditFinding.deleted_at.is_(None),
                )
            ).scalar_one_or_none()
            if row is None:
                failed_ids.append(finding_id)
                continue

            allowed = self.ALLOWED_TRANSITIONS.get(row.status, set())
            if new_status not in allowed:
                failed_ids.append(finding_id)
                continue

            row.status = new_status
            if new_status in {"closed", "risk_accepted"}:
                row.closed_at = self.utcnow()
                row.closed_by = user_id
            else:
                row.closed_at = None
                row.closed_by = None
            updated_count += 1

        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="audit_finding.bulk_transitioned",
            entity_type="audit_finding",
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={
                "new_status": new_status,
                "updated_count": updated_count,
                "failed_ids": [str(item) for item in failed_ids],
            },
            metadata_json={"source": "api"},
        )
        return {"updated_count": updated_count, "failed_ids": failed_ids}

    def get_finding_summary(self, org_id: uuid.UUID, engagement_id: uuid.UUID | None = None) -> dict:
        stmt = select(AuditFinding).where(
            AuditFinding.organization_id == org_id,
            AuditFinding.deleted_at.is_(None),
        )
        if engagement_id is not None:
            stmt = stmt.where(AuditFinding.audit_engagement_id == engagement_id)
        rows = self.db.execute(stmt).scalars().all()

        by_severity: dict[str, int] = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "informational": 0,
        }
        by_status: dict[str, int] = {
            "open": 0,
            "in_remediation": 0,
            "remediated": 0,
            "closed": 0,
            "risk_accepted": 0,
        }

        today = self.utcdate()
        overdue_count = 0
        open_critical_count = 0
        linked_to_risk_count = 0

        for row in rows:
            by_severity[row.severity] = by_severity.get(row.severity, 0) + 1
            by_status[row.status] = by_status.get(row.status, 0) + 1

            is_terminal = row.status in {"closed", "risk_accepted"}
            if row.severity == "critical" and not is_terminal:
                open_critical_count += 1
            if row.target_remediation_date < today and not is_terminal:
                overdue_count += 1
            if row.risk_register_entry_id is not None:
                linked_to_risk_count += 1

        return {
            "total": len(rows),
            "by_severity": by_severity,
            "by_status": by_status,
            "open_critical_count": open_critical_count,
            "overdue_count": overdue_count,
            "linked_to_risk_count": linked_to_risk_count,
        }

    def soft_delete_finding(self, org_id: uuid.UUID, finding_id: uuid.UUID, user_id: uuid.UUID) -> AuditFinding:
        row = self.require_finding(org_id, finding_id)
        if row.status != "open":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only open findings can be deleted")

        row.deleted_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="audit_finding.deleted",
            entity_type="audit_finding",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"deleted_at": row.deleted_at.isoformat() if row.deleted_at else None, "status": row.status},
            metadata_json={"source": "api"},
        )
        return row
