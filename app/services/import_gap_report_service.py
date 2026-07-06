from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ai_system import AISystem
from app.models.compliance_policy import CompliancePolicy
from app.models.control import Control
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.framework import Framework
from app.models.import_job import ImportJob
from app.models.obligation import Obligation
from app.models.organization_framework import OrganizationFramework
from app.models.vendor import Vendor


class ImportGapReportService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(UTC)

    def _require_job(self, organization_id: uuid.UUID, job_id: uuid.UUID) -> ImportJob:
        row = self.db.execute(
            select(ImportJob).where(
                ImportJob.organization_id == organization_id,
                ImportJob.id == job_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found")
        return row

    def _active_frameworks(self, organization_id: uuid.UUID) -> list[tuple[OrganizationFramework, Framework]]:
        return self.db.execute(
            select(OrganizationFramework, Framework)
            .join(Framework, Framework.id == OrganizationFramework.framework_id)
            .where(
                OrganizationFramework.organization_id == organization_id,
                OrganizationFramework.status == "active",
                Framework.status == "active",
            )
            .order_by(Framework.name.asc())
        ).all()

    def _import_signal_corpus(self, organization_id: uuid.UUID) -> str:
        parts: list[str] = []
        control_rows = self.db.execute(
            select(Control.title, Control.description).where(
                Control.organization_id == organization_id,
                Control.status != "archived",
                Control.source_import_tool.is_not(None),
            )
        ).all()
        policy_rows = self.db.execute(
            select(CompliancePolicy.title, CompliancePolicy.description).where(
                CompliancePolicy.organization_id == organization_id,
                CompliancePolicy.archived_at.is_(None),
                CompliancePolicy.source_import_tool.is_not(None),
            )
        ).all()
        evidence_rows = self.db.execute(
            select(EvidenceItem.title, EvidenceItem.description).where(
                EvidenceItem.organization_id == organization_id,
                EvidenceItem.status != "archived",
                EvidenceItem.source_import_tool.is_not(None),
            )
        ).all()
        for title, description in [*control_rows, *policy_rows, *evidence_rows]:
            if title:
                parts.append(str(title))
            if description:
                parts.append(str(description))
        return " ".join(parts).lower()

    def _is_stale(self, job: ImportJob) -> tuple[bool, str | None]:
        newer_job = self.db.execute(
            select(ImportJob.id, ImportJob.updated_at)
            .where(
                ImportJob.organization_id == job.organization_id,
                ImportJob.id != job.id,
                ImportJob.status.in_(["preview_ready", "completed"]),
                ImportJob.updated_at > job.updated_at,
            )
            .order_by(ImportJob.updated_at.desc())
            .limit(1)
        ).first()
        if newer_job is None:
            return False, None
        newer_id, newer_updated_at = newer_job
        return (
            True,
            f"Newer import job {newer_id} completed at {newer_updated_at.isoformat()} and may change coverage gaps.",
        )

    def generate(self, organization_id: uuid.UUID, job_id: uuid.UUID) -> dict:
        job = self._require_job(organization_id, job_id)
        framework_rows = self._active_frameworks(organization_id)
        framework_ids = [framework.id for _, framework in framework_rows]
        imported_text = self._import_signal_corpus(organization_id)
        stale, stale_reason = self._is_stale(job)

        obligations_without_coverage: list[dict] = []
        controls_without_coverage: list[dict] = []
        ai_systems_without_coverage: list[dict] = []
        vendors_without_coverage: list[dict] = []

        if framework_ids:
            obligations = self.db.execute(
                select(Obligation.id, Obligation.reference_code, Obligation.title)
                .where(
                    Obligation.framework_id.in_(framework_ids),
                    Obligation.status == "active",
                )
                .order_by(Obligation.reference_code.asc(), Obligation.title.asc())
            ).all()
            for obligation_id, reference_code, title in obligations:
                mapped_count = int(
                    self.db.execute(
                        select(func.count(func.distinct(ControlObligationMapping.control_id)))
                        .join(Control, Control.id == ControlObligationMapping.control_id)
                        .where(
                            ControlObligationMapping.organization_id == organization_id,
                            ControlObligationMapping.obligation_id == obligation_id,
                            ControlObligationMapping.status == "active",
                            Control.organization_id == organization_id,
                            Control.status != "archived",
                            Control.source_import_tool.is_not(None),
                        )
                    ).scalar_one()
                )
                if mapped_count == 0:
                    obligations_without_coverage.append(
                        {
                            "id": obligation_id,
                            "name": f"{reference_code} - {title}",
                            "reason": "No active control mapping backed by imported controls.",
                        }
                    )

        controls = self.db.execute(
            select(Control.id, Control.title, Control.source_import_tool)
            .where(
                Control.organization_id == organization_id,
                Control.status != "archived",
            )
            .order_by(Control.title.asc())
        ).all()
        for control_id, title, source_import_tool in controls:
            if source_import_tool:
                continue
            imported_link_count = int(
                self.db.execute(
                    select(func.count(EvidenceControlLink.id))
                    .join(EvidenceItem, EvidenceItem.id == EvidenceControlLink.evidence_item_id)
                    .where(
                        EvidenceControlLink.organization_id == organization_id,
                        EvidenceControlLink.control_id == control_id,
                        EvidenceControlLink.link_status == "active",
                        EvidenceItem.organization_id == organization_id,
                        EvidenceItem.status != "archived",
                        EvidenceItem.source_import_tool.is_not(None),
                    )
                ).scalar_one()
            )
            if imported_link_count == 0:
                controls_without_coverage.append(
                    {
                        "id": control_id,
                        "name": title,
                        "reason": "No imported control ownership and no imported evidence linked to this control.",
                    }
                )

        ai_rows = self.db.execute(
            select(AISystem.id, AISystem.name, AISystem.vendor_name, AISystem.provider_name, AISystem.model_name)
            .where(
                AISystem.organization_id == organization_id,
                AISystem.deleted_at.is_(None),
                AISystem.archived_at.is_(None),
            )
            .order_by(AISystem.name.asc())
        ).all()
        for ai_id, name, vendor_name, provider_name, model_name in ai_rows:
            tokens = [name, vendor_name, provider_name, model_name]
            has_signal = any(token and str(token).lower() in imported_text for token in tokens)
            if not has_signal:
                ai_systems_without_coverage.append(
                    {
                        "id": ai_id,
                        "name": name,
                        "reason": "No imported policy/control/evidence text references this AI system.",
                    }
                )

        vendor_rows = self.db.execute(
            select(Vendor.id, Vendor.name)
            .where(
                Vendor.organization_id == organization_id,
                Vendor.status == "active",
                Vendor.archived_at.is_(None),
            )
            .order_by(Vendor.name.asc())
        ).all()
        for vendor_id, name in vendor_rows:
            if name.lower() in imported_text:
                continue
            vendors_without_coverage.append(
                {
                    "id": vendor_id,
                    "name": name,
                    "reason": "No imported policy/control/evidence text references this vendor.",
                }
            )

        return {
            "job_id": job.id,
            "generated_at": self._utcnow(),
            "import_source": job.source_tool,
            "stale": stale,
            "stale_reason": stale_reason,
            "active_frameworks": [
                {
                    "framework_id": framework.id,
                    "code": framework.code,
                    "name": framework.name,
                }
                for _, framework in framework_rows
            ],
            "obligations_without_coverage": obligations_without_coverage,
            "controls_without_coverage": controls_without_coverage,
            "ai_systems_without_coverage": ai_systems_without_coverage,
            "vendors_without_coverage": vendors_without_coverage,
            "summary": {
                "framework_count": len(framework_rows),
                "obligation_gap_count": len(obligations_without_coverage),
                "control_gap_count": len(controls_without_coverage),
                "ai_system_gap_count": len(ai_systems_without_coverage),
                "vendor_gap_count": len(vendors_without_coverage),
            },
        }
