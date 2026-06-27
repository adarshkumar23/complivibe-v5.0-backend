import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.control import Control
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.framework import Framework
from app.models.framework_section import FrameworkSection
from app.models.obligation import Obligation
from app.models.organization_framework import OrganizationFramework


class FrameworkCoverageMatrixService:
    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _validate_framework_for_org(org_id: uuid.UUID, framework_id: uuid.UUID, db: Session) -> Framework:
        framework = db.get(Framework, framework_id)
        if framework is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework not found")

        org_framework = db.execute(
            select(OrganizationFramework).where(
                OrganizationFramework.organization_id == org_id,
                OrganizationFramework.framework_id == framework_id,
                OrganizationFramework.status == "active",
            )
        ).scalar_one_or_none()
        if org_framework is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework not configured for organization")
        return framework

    @staticmethod
    def _default_section_title(obligation: Obligation) -> str:
        ref = obligation.reference_code or ""
        if "." in ref:
            return ref.split(".", 1)[0]
        return ref or "General"

    @staticmethod
    def _normalize_uuid_list(values: list) -> list[uuid.UUID]:
        normalized: list[uuid.UUID] = []
        for value in values:
            if value is None:
                continue
            if isinstance(value, uuid.UUID):
                normalized.append(value)
            else:
                normalized.append(uuid.UUID(str(value)))
        return normalized

    def build(self, framework_id: uuid.UUID, org_id: uuid.UUID, db: Session) -> dict:
        _ = db
        framework = self._validate_framework_for_org(org_id, framework_id, self.db)
        now = self._now()

        obligations = self.db.execute(
            select(Obligation)
            .where(
                Obligation.framework_id == framework_id,
                Obligation.status == "active",
            )
            .order_by(Obligation.reference_code.asc())
        ).scalars().all()

        section_titles = {
            row.id: row.title
            for row in self.db.execute(
                select(FrameworkSection).where(FrameworkSection.framework_id == framework_id)
            ).scalars().all()
        }

        covered = partial = uncovered = 0
        sections_map: dict[str, list[dict]] = {}

        for obligation in obligations:
            control_ids = self.db.execute(
                select(func.distinct(ControlObligationMapping.control_id))
                .join(Control, Control.id == ControlObligationMapping.control_id)
                .where(
                    ControlObligationMapping.organization_id == org_id,
                    ControlObligationMapping.obligation_id == obligation.id,
                    ControlObligationMapping.status == "active",
                    Control.organization_id == org_id,
                    Control.status != "archived",
                )
            ).scalars().all()
            control_ids = self._normalize_uuid_list(control_ids)
            controls_count = len(control_ids)

            evidence_count = 0
            if control_ids:
                evidence_count = int(
                    self.db.execute(
                        select(func.count(func.distinct(EvidenceItem.id)))
                        .join(EvidenceControlLink, EvidenceControlLink.evidence_item_id == EvidenceItem.id)
                        .where(
                            EvidenceControlLink.organization_id == org_id,
                            EvidenceControlLink.control_id.in_(control_ids),
                            EvidenceControlLink.link_status == "active",
                            EvidenceItem.organization_id == org_id,
                            EvidenceItem.status == "active",
                            EvidenceItem.review_status == "verified",
                            ((EvidenceItem.valid_until.is_(None)) | (EvidenceItem.valid_until > now)),
                        )
                    ).scalar_one()
                )

            if controls_count == 0:
                coverage_status = "uncovered"
                uncovered += 1
            elif evidence_count == 0:
                coverage_status = "partial"
                partial += 1
            else:
                coverage_status = "covered"
                covered += 1

            section_title = section_titles.get(obligation.framework_section_id) if obligation.framework_section_id else None
            if not section_title:
                section_title = self._default_section_title(obligation)

            sections_map.setdefault(section_title, []).append(
                {
                    "obligation_id": str(obligation.id),
                    "reference": obligation.reference_code,
                    "title": obligation.title,
                    "controls_count": controls_count,
                    "evidence_count": evidence_count,
                    "coverage_status": coverage_status,
                }
            )

        sections = [
            {
                "section_title": title,
                "obligations": sorted(items, key=lambda item: (item.get("reference") or "", item.get("title") or "")),
            }
            for title, items in sorted(sections_map.items(), key=lambda pair: pair[0])
        ]

        total = len(obligations)
        coverage_pct = round((covered / total) * 100.0, 2) if total else 0.0
        return {
            "framework_id": str(framework_id),
            "framework_name": framework.name,
            "total_obligations": total,
            "covered": covered,
            "partial": partial,
            "uncovered": uncovered,
            "coverage_pct": coverage_pct,
            "sections": sections,
        }

    def __init__(self, db: Session) -> None:
        self.db = db
