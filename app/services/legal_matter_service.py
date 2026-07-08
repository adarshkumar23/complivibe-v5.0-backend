import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.compliance.services.issue_service import IssueService
from app.models.control import Control
from app.models.evidence_item import EvidenceItem
from app.models.issue import Issue
from app.models.legal_matter import LegalMatter
from app.models.legal_matter_control_link import LegalMatterControlLink
from app.models.legal_matter_evidence_link import LegalMatterEvidenceLink
from app.models.membership import Membership
from app.models.risk import Risk
from app.models.user import User
from app.schemas.legal_matter import LegalMatterCreate, LegalMatterUpdate
from app.services.audit_service import AuditService

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
OPEN_ISSUE_STATUSES = {"open", "investigating", "mitigating"}


class LegalMatterService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _require_active_org_user(self, org_id: uuid.UUID, user_id: uuid.UUID, field_name: str) -> None:
        row = self.db.execute(
            select(User.id)
            .join(Membership, Membership.user_id == User.id)
            .where(
                User.id == user_id,
                User.is_active.is_(True),
                User.status == "active",
                Membership.organization_id == org_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{field_name} must be an active organization user",
            )

    def create_matter(self, org_id: uuid.UUID, data: LegalMatterCreate, created_by: uuid.UUID) -> LegalMatter:
        if data.owner_user_id is not None:
            self._require_active_org_user(org_id, data.owner_user_id, "owner_user_id")
        row = LegalMatter(
            organization_id=org_id,
            title=data.title,
            description=data.description,
            matter_type=data.matter_type,
            status="open",
            opposing_party=data.opposing_party,
            outside_counsel=data.outside_counsel,
            budget=data.budget,
            owner_user_id=data.owner_user_id,
            opened_at=data.opened_at or self.utcnow(),
            created_by=created_by,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="legal_matter.created",
            entity_type="legal_matter",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={
                "title": row.title,
                "matter_type": row.matter_type,
                "status": row.status,
            },
            metadata_json={"source": "api"},
        )
        return row

    def get_matter(self, org_id: uuid.UUID, matter_id: uuid.UUID) -> LegalMatter:
        row = self.db.execute(
            select(LegalMatter).where(
                LegalMatter.organization_id == org_id,
                LegalMatter.id == matter_id,
                LegalMatter.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Legal matter not found")
        return row

    def list_matters(
        self,
        org_id: uuid.UUID,
        *,
        status_value: str | None = None,
        matter_type: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[LegalMatter]:
        stmt = select(LegalMatter).where(
            LegalMatter.organization_id == org_id,
            LegalMatter.deleted_at.is_(None),
        )
        if status_value is not None:
            stmt = stmt.where(LegalMatter.status == status_value)
        if matter_type is not None:
            stmt = stmt.where(LegalMatter.matter_type == matter_type)

        stmt = stmt.order_by(LegalMatter.created_at.desc()).offset(skip).limit(limit)
        return self.db.execute(stmt).scalars().all()

    def update_matter(
        self, org_id: uuid.UUID, matter_id: uuid.UUID, data: LegalMatterUpdate, actor_id: uuid.UUID | None = None
    ) -> LegalMatter:
        row = self.get_matter(org_id, matter_id)
        # `status` is deliberately absent from LegalMatterUpdate: lifecycle transitions
        # must go through change_status() / close_matter() so the open-linked-issue
        # guard and closed_at/closed_by bookkeeping can never be bypassed by a plain PATCH.
        updates = data.model_dump(exclude_unset=True)
        if updates.get("owner_user_id") is not None:
            self._require_active_org_user(org_id, updates["owner_user_id"], "owner_user_id")

        before = {"title": row.title, "status": row.status, "matter_type": row.matter_type}
        for key, value in updates.items():
            setattr(row, key, value)

        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="legal_matter.updated",
            entity_type="legal_matter",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            before_json=before,
            after_json={"title": row.title, "status": row.status, "matter_type": row.matter_type},
            metadata_json={"source": "api"},
        )
        return row

    def change_status(
        self, org_id: uuid.UUID, matter_id: uuid.UUID, new_status: str, actor_id: uuid.UUID | None = None
    ) -> LegalMatter:
        """Transition a matter between the non-terminal statuses (open/in_progress/on_hold),
        including reopening a closed matter. Closing must go through close_matter()."""
        row = self.get_matter(org_id, matter_id)
        if row.status == new_status:
            return row

        was_closed = row.status == "closed"
        before = {"status": row.status, "closed_at": row.closed_at.isoformat() if row.closed_at else None}
        row.status = new_status
        if was_closed:
            # Reopening: clear stale closure bookkeeping so it doesn't misrepresent
            # a reopened matter as still having a closed_at/closed_by.
            row.closed_at = None
            row.closed_by = None
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="legal_matter.reopened" if was_closed else "legal_matter.status_changed",
            entity_type="legal_matter",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            before_json=before,
            after_json={"status": row.status, "closed_at": None},
            metadata_json={"source": "api"},
        )
        return row

    def _get_org_risk(self, org_id: uuid.UUID, risk_id: uuid.UUID) -> Risk:
        risk = self.db.execute(
            select(Risk).where(Risk.id == risk_id, Risk.organization_id == org_id)
        ).scalar_one_or_none()
        if risk is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk not found")
        return risk

    @staticmethod
    def _reject_if_closed(row: LegalMatter, action: str) -> None:
        if row.status == "closed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot {action} on a closed legal matter; reopen it first via /status",
            )

    def link_risk(self, org_id: uuid.UUID, matter_id: uuid.UUID, risk_id: uuid.UUID, actor_id: uuid.UUID | None = None) -> LegalMatter:
        row = self.get_matter(org_id, matter_id)
        # The closed-matter guardrail must apply consistently regardless of whether
        # this call is a no-op (re-linking the already-linked risk) -- a closed matter
        # rejects ANY link attempt, matching the fresh-risk case below. Checking this
        # before the idempotency short-circuit closes a gap where re-submitting the
        # same risk_id on a closed matter silently 200'd instead of 409ing.
        self._reject_if_closed(row, "link a risk")
        if row.related_risk_id == risk_id:
            return row

        risk = self._get_org_risk(org_id, risk_id)

        before = {"related_risk_id": str(row.related_risk_id) if row.related_risk_id else None}
        row.related_risk_id = risk.id
        row.risk_severity_at_link = risk.severity
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="legal_matter.risk_linked",
            entity_type="legal_matter",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            before_json=before,
            after_json={"related_risk_id": str(risk.id), "risk_severity_at_link": risk.severity},
            metadata_json={"source": "api"},
        )
        return row

    def unlink_risk(self, org_id: uuid.UUID, matter_id: uuid.UUID, actor_id: uuid.UUID | None = None) -> LegalMatter:
        row = self.get_matter(org_id, matter_id)
        before = {"related_risk_id": str(row.related_risk_id) if row.related_risk_id else None}
        row.related_risk_id = None
        row.risk_severity_at_link = None
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="legal_matter.risk_unlinked",
            entity_type="legal_matter",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            before_json=before,
            after_json={"related_risk_id": None},
            metadata_json={"source": "api"},
        )
        return row

    def link_issue(self, org_id: uuid.UUID, matter_id: uuid.UUID, issue_id: uuid.UUID, actor_id: uuid.UUID | None = None) -> LegalMatter:
        row = self.get_matter(org_id, matter_id)
        # See link_risk() above: the closed-matter guardrail must be checked BEFORE
        # the idempotency short-circuit, or re-submitting the same already-linked
        # issue on a closed matter silently 200s instead of 409ing like a fresh link
        # attempt does. Closed means closed, regardless of whether the link is a no-op.
        self._reject_if_closed(row, "link an issue")
        if row.related_issue_id == issue_id:
            return row

        issue = IssueService(self.db).get_issue(org_id, issue_id)

        before = {"related_issue_id": str(row.related_issue_id) if row.related_issue_id else None}
        row.related_issue_id = issue.id
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="legal_matter.issue_linked",
            entity_type="legal_matter",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            before_json=before,
            after_json={"related_issue_id": str(issue.id)},
            metadata_json={"source": "api"},
        )
        return row

    def unlink_issue(self, org_id: uuid.UUID, matter_id: uuid.UUID, actor_id: uuid.UUID | None = None) -> LegalMatter:
        row = self.get_matter(org_id, matter_id)
        before = {"related_issue_id": str(row.related_issue_id) if row.related_issue_id else None}
        row.related_issue_id = None
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="legal_matter.issue_unlinked",
            entity_type="legal_matter",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            before_json=before,
            after_json={"related_issue_id": None},
            metadata_json={"source": "api"},
        )
        return row

    def _get_org_evidence(self, org_id: uuid.UUID, evidence_id: uuid.UUID) -> EvidenceItem:
        evidence = self.db.execute(
            select(EvidenceItem).where(EvidenceItem.id == evidence_id, EvidenceItem.organization_id == org_id)
        ).scalar_one_or_none()
        if evidence is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence item not found")
        return evidence

    def _get_org_control(self, org_id: uuid.UUID, control_id: uuid.UUID) -> Control:
        control = self.db.execute(
            select(Control).where(Control.id == control_id, Control.organization_id == org_id)
        ).scalar_one_or_none()
        if control is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control not found")
        return control

    def link_evidence(
        self, org_id: uuid.UUID, matter_id: uuid.UUID, evidence_id: uuid.UUID, actor_id: uuid.UUID | None = None
    ) -> LegalMatterEvidenceLink:
        row = self.get_matter(org_id, matter_id)
        # Same closed-matter guardrail as link_risk/link_issue, checked before any
        # idempotency short-circuit (see G9 item 15): closed means closed.
        self._reject_if_closed(row, "link evidence")
        evidence = self._get_org_evidence(org_id, evidence_id)

        existing = self.db.execute(
            select(LegalMatterEvidenceLink).where(
                LegalMatterEvidenceLink.organization_id == org_id,
                LegalMatterEvidenceLink.matter_id == matter_id,
                LegalMatterEvidenceLink.evidence_id == evidence_id,
            )
        ).scalar_one_or_none()
        now = self.utcnow()
        if existing is not None:
            if existing.status == "active":
                return existing
            existing.status = "active"
            existing.linked_by_user_id = actor_id
            existing.linked_at = now
            existing.unlinked_at = None
            link = existing
        else:
            link = LegalMatterEvidenceLink(
                organization_id=org_id,
                matter_id=matter_id,
                evidence_id=evidence.id,
                status="active",
                linked_by_user_id=actor_id,
                linked_at=now,
            )
            self.db.add(link)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="legal_matter.evidence_linked",
            entity_type="legal_matter",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            after_json={"evidence_id": str(evidence.id)},
            metadata_json={"source": "api"},
        )
        return link

    def unlink_evidence(
        self, org_id: uuid.UUID, matter_id: uuid.UUID, evidence_id: uuid.UUID, actor_id: uuid.UUID | None = None
    ) -> None:
        row = self.get_matter(org_id, matter_id)
        link = self.db.execute(
            select(LegalMatterEvidenceLink).where(
                LegalMatterEvidenceLink.organization_id == org_id,
                LegalMatterEvidenceLink.matter_id == matter_id,
                LegalMatterEvidenceLink.evidence_id == evidence_id,
                LegalMatterEvidenceLink.status == "active",
            )
        ).scalar_one_or_none()
        if link is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence link not found")

        link.status = "inactive"
        link.unlinked_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="legal_matter.evidence_unlinked",
            entity_type="legal_matter",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            after_json={"evidence_id": str(evidence_id)},
            metadata_json={"source": "api"},
        )

    def list_linked_evidence(self, org_id: uuid.UUID, matter_id: uuid.UUID) -> list[LegalMatterEvidenceLink]:
        self.get_matter(org_id, matter_id)
        return list(
            self.db.execute(
                select(LegalMatterEvidenceLink).where(
                    LegalMatterEvidenceLink.organization_id == org_id,
                    LegalMatterEvidenceLink.matter_id == matter_id,
                    LegalMatterEvidenceLink.status == "active",
                )
            ).scalars().all()
        )

    def count_linked_evidence(self, org_id: uuid.UUID, matter_id: uuid.UUID) -> int:
        return int(
            self.db.execute(
                select(func.count(LegalMatterEvidenceLink.id)).where(
                    LegalMatterEvidenceLink.organization_id == org_id,
                    LegalMatterEvidenceLink.matter_id == matter_id,
                    LegalMatterEvidenceLink.status == "active",
                )
            ).scalar_one()
        )

    def link_control(
        self, org_id: uuid.UUID, matter_id: uuid.UUID, control_id: uuid.UUID, actor_id: uuid.UUID | None = None
    ) -> LegalMatterControlLink:
        row = self.get_matter(org_id, matter_id)
        self._reject_if_closed(row, "link a control")
        control = self._get_org_control(org_id, control_id)

        existing = self.db.execute(
            select(LegalMatterControlLink).where(
                LegalMatterControlLink.organization_id == org_id,
                LegalMatterControlLink.matter_id == matter_id,
                LegalMatterControlLink.control_id == control_id,
            )
        ).scalar_one_or_none()
        now = self.utcnow()
        if existing is not None:
            if existing.status == "active":
                return existing
            existing.status = "active"
            existing.linked_by_user_id = actor_id
            existing.linked_at = now
            existing.unlinked_at = None
            link = existing
        else:
            link = LegalMatterControlLink(
                organization_id=org_id,
                matter_id=matter_id,
                control_id=control.id,
                status="active",
                linked_by_user_id=actor_id,
                linked_at=now,
            )
            self.db.add(link)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="legal_matter.control_linked",
            entity_type="legal_matter",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            after_json={"control_id": str(control.id)},
            metadata_json={"source": "api"},
        )
        return link

    def unlink_control(
        self, org_id: uuid.UUID, matter_id: uuid.UUID, control_id: uuid.UUID, actor_id: uuid.UUID | None = None
    ) -> None:
        row = self.get_matter(org_id, matter_id)
        link = self.db.execute(
            select(LegalMatterControlLink).where(
                LegalMatterControlLink.organization_id == org_id,
                LegalMatterControlLink.matter_id == matter_id,
                LegalMatterControlLink.control_id == control_id,
                LegalMatterControlLink.status == "active",
            )
        ).scalar_one_or_none()
        if link is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control link not found")

        link.status = "inactive"
        link.unlinked_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="legal_matter.control_unlinked",
            entity_type="legal_matter",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            after_json={"control_id": str(control_id)},
            metadata_json={"source": "api"},
        )

    def list_linked_controls(self, org_id: uuid.UUID, matter_id: uuid.UUID) -> list[LegalMatterControlLink]:
        self.get_matter(org_id, matter_id)
        return list(
            self.db.execute(
                select(LegalMatterControlLink).where(
                    LegalMatterControlLink.organization_id == org_id,
                    LegalMatterControlLink.matter_id == matter_id,
                    LegalMatterControlLink.status == "active",
                )
            ).scalars().all()
        )

    def count_linked_controls(self, org_id: uuid.UUID, matter_id: uuid.UUID) -> int:
        return int(
            self.db.execute(
                select(func.count(LegalMatterControlLink.id)).where(
                    LegalMatterControlLink.organization_id == org_id,
                    LegalMatterControlLink.matter_id == matter_id,
                    LegalMatterControlLink.status == "active",
                )
            ).scalar_one()
        )

    def close_matter(
        self, org_id: uuid.UUID, matter_id: uuid.UUID, *, confirm: bool, actor_id: uuid.UUID | None = None
    ) -> LegalMatter:
        row = self.get_matter(org_id, matter_id)

        if row.related_issue_id is not None:
            issue = self.db.execute(
                select(Issue).where(Issue.id == row.related_issue_id, Issue.organization_id == org_id)
            ).scalar_one_or_none()
            if issue is not None and issue.status in OPEN_ISSUE_STATUSES and not confirm:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Matter has an open linked issue (status={issue.status}); "
                        "pass confirm=true to close anyway"
                    ),
                )

        before = {"status": row.status}
        row.status = "closed"
        row.closed_at = self.utcnow()
        row.closed_by = actor_id
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="legal_matter.closed",
            entity_type="legal_matter",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            before_json=before,
            after_json={"status": row.status, "closed_at": row.closed_at.isoformat()},
            metadata_json={"source": "api"},
        )
        return row

    def get_escalation_status(self, org_id: uuid.UUID, row: LegalMatter) -> bool:
        if row.related_risk_id is None or row.risk_severity_at_link is None:
            return False

        risk = self.db.execute(
            select(Risk).where(Risk.id == row.related_risk_id, Risk.organization_id == org_id)
        ).scalar_one_or_none()
        if risk is None:
            return False

        linked_ordinal = SEVERITY_ORDER.get(row.risk_severity_at_link, -1)
        current_ordinal = SEVERITY_ORDER.get(risk.severity, -1)
        return current_ordinal > linked_ordinal

    def get_open_linked_issue_warning(self, org_id: uuid.UUID, row: LegalMatter) -> str | None:
        if row.related_issue_id is None:
            return None

        issue = self.db.execute(
            select(Issue).where(Issue.id == row.related_issue_id, Issue.organization_id == org_id)
        ).scalar_one_or_none()
        if issue is None or issue.status not in OPEN_ISSUE_STATUSES:
            return None

        return f"Linked issue is still open (status={issue.status})"
