import uuid
from collections import Counter
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_governance.services.ai_governance_event_service import AIGovernanceEventService
from app.models.framework import Framework
from app.models.iso42001_conformity_tracker import ISO42001ConformityTracker
from app.models.obligation import Obligation
from app.services.audit_service import AuditService
from app.services.seed_service import ISO42001_OBLIGATIONS, SeedService

ALLOWED_TRACKER_STATUS = {"not_started", "in_progress", "implemented", "verified"}


class ISO42001Service:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _clause_sort_key(clause_ref: str) -> tuple[int, ...]:
        parts: list[int] = []
        for part in clause_ref.split("."):
            try:
                parts.append(int(part))
            except ValueError:
                parts.append(0)
        return tuple(parts)

    def _iso_framework(self) -> Framework:
        framework = self.db.execute(select(Framework).where(Framework.code == "ISO_42001")).scalar_one_or_none()
        if framework is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ISO 42001 framework not found")
        return framework

    def _seeded_iso_clause_refs(self) -> set[str]:
        return {ref for ref, _ in ISO42001_OBLIGATIONS}

    def _iso_obligations(self) -> list[Obligation]:
        SeedService.ensure_starter_obligations(self.db)
        framework = self._iso_framework()
        stmt = (
            select(Obligation)
            .where(
                Obligation.framework_id == framework.id,
                Obligation.status == "active",
                Obligation.reference_code.in_(self._seeded_iso_clause_refs()),
            )
            .order_by(Obligation.reference_code.asc())
        )
        rows = self.db.execute(stmt).scalars().all()
        rows.sort(key=lambda row: self._clause_sort_key(row.reference_code))
        return rows

    def get_or_create_trackers(self, org_id: uuid.UUID) -> list[ISO42001ConformityTracker]:
        obligations = self._iso_obligations()
        existing = {
            row.clause_ref: row
            for row in self.db.execute(
                select(ISO42001ConformityTracker).where(ISO42001ConformityTracker.organization_id == org_id)
            ).scalars().all()
        }

        now = self.utcnow()
        for obligation in obligations:
            tracker = existing.get(obligation.reference_code)
            if tracker is None:
                tracker = ISO42001ConformityTracker(
                    organization_id=org_id,
                    clause_ref=obligation.reference_code,
                    implementation_status="not_started",
                    notes=None,
                    evidence_id=None,
                    updated_by=None,
                    created_at=now,
                    updated_at=now,
                )
                self.db.add(tracker)
                self.db.flush()
                existing[obligation.reference_code] = tracker

        return sorted(existing.values(), key=lambda row: self._clause_sort_key(row.clause_ref))

    def update_tracker(
        self,
        org_id: uuid.UUID,
        clause_ref: str,
        status_value: str,
        notes: str | None,
        evidence_id: uuid.UUID | None,
        user_id: uuid.UUID,
    ) -> ISO42001ConformityTracker:
        if status_value not in ALLOWED_TRACKER_STATUS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid implementation status")

        clause_refs = {row.reference_code for row in self._iso_obligations()}
        if clause_ref not in clause_refs:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ISO 42001 clause not found")

        row = self.db.execute(
            select(ISO42001ConformityTracker).where(
                ISO42001ConformityTracker.organization_id == org_id,
                ISO42001ConformityTracker.clause_ref == clause_ref,
            )
        ).scalar_one_or_none()

        now = self.utcnow()
        if row is None:
            row = ISO42001ConformityTracker(
                organization_id=org_id,
                clause_ref=clause_ref,
                implementation_status=status_value,
                notes=notes,
                evidence_id=evidence_id,
                updated_by=user_id,
                created_at=now,
                updated_at=now,
            )
            self.db.add(row)
            self.db.flush()
        else:
            row.implementation_status = status_value
            row.notes = notes
            row.evidence_id = evidence_id
            row.updated_by = user_id
            row.updated_at = now
            self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "iso42001.tracker_updated",
            actor_id=user_id,
            actor_type="user",
            event_data={
                "clause_ref": clause_ref,
                "implementation_status": status_value,
                "evidence_id": str(evidence_id) if evidence_id else None,
            },
        )
        AuditService(self.db).write_audit_log(
            action="iso42001.tracker_updated",
            entity_type="iso42001_conformity_tracker",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={
                "clause_ref": row.clause_ref,
                "implementation_status": row.implementation_status,
                "evidence_id": str(row.evidence_id) if row.evidence_id else None,
            },
            metadata_json={"source": "api"},
        )
        return row

    def get_conformity_summary(self, org_id: uuid.UUID) -> dict:
        rows = self.get_or_create_trackers(org_id)
        total = len(rows)
        counts = Counter(row.implementation_status for row in rows)
        completed_count = int(counts.get("implemented", 0) + counts.get("verified", 0))
        implementation_pct = round((completed_count / total) * 100, 2) if total else 0.0

        section_totals: dict[str, int] = {}
        section_completed: dict[str, int] = {}
        for row in rows:
            clause_prefix = row.clause_ref.split(".", 1)[0]
            section = f"Clause {clause_prefix}"
            section_totals[section] = section_totals.get(section, 0) + 1
            if row.implementation_status in {"implemented", "verified"}:
                section_completed[section] = section_completed.get(section, 0) + 1

        ordered_sections = sorted(section_totals.keys(), key=lambda key: self._clause_sort_key(key.replace("Clause ", "")))
        sections = {
            section: {
                "total": section_totals[section],
                "implemented": section_completed.get(section, 0),
                "pct": round((section_completed.get(section, 0) / section_totals[section]) * 100, 2) if section_totals[section] else 0.0,
            }
            for section in ordered_sections
        }

        by_status = {status_name: int(counts.get(status_name, 0)) for status_name in sorted(ALLOWED_TRACKER_STATUS)}
        return {
            "total_clauses": total,
            "by_status": by_status,
            "implementation_pct": implementation_pct,
            "sections": sections,
        }
