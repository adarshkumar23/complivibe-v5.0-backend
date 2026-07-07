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
        if row.status in {"queued", "processing"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Import job is still in progress; gap report is available after import processing finishes",
            )
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
        now = self._utcnow()
        job_updated_at = job.updated_at if job.updated_at.tzinfo else job.updated_at.replace(tzinfo=UTC)
        data_age_hours = round((now - job_updated_at).total_seconds() / 3600.0, 2)

        obligations_without_coverage: list[dict] = []
        controls_without_coverage: list[dict] = []
        ai_systems_without_coverage: list[dict] = []
        vendors_without_coverage: list[dict] = []
        obligations_total = 0
        controls_total = 0
        ai_systems_total = 0
        vendors_total = 0

        if framework_ids:
            obligations = self.db.execute(
                select(Obligation.id, Obligation.reference_code, Obligation.title)
                .where(
                    Obligation.framework_id.in_(framework_ids),
                    Obligation.status == "active",
                )
                .order_by(Obligation.reference_code.asc(), Obligation.title.asc())
            ).all()
            obligations_total = len(obligations)
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
        controls_total = len(controls)
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
        ai_systems_total = len(ai_rows)
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
        vendors_total = len(vendor_rows)
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

        def _coverage_pct(total: int, gap_count: int) -> float:
            if total <= 0:
                return 100.0
            return round(((total - gap_count) / total) * 100.0, 2)

        context_flags: list[str] = []
        if not framework_rows:
            context_flags.append("no_active_frameworks")
        if stale:
            context_flags.append("gap_report_stale")
        if not imported_text.strip():
            context_flags.append("import_signal_corpus_empty")
        if obligations_without_coverage:
            context_flags.append("obligation_coverage_gaps_present")
        if controls_without_coverage:
            context_flags.append("control_coverage_gaps_present")
        if ai_systems_without_coverage:
            context_flags.append("ai_system_coverage_gaps_present")
        if vendors_without_coverage:
            context_flags.append("vendor_coverage_gaps_present")

        domain_gap_counts = {
            "obligations": len(obligations_without_coverage),
            "controls": len(controls_without_coverage),
            "ai_systems": len(ai_systems_without_coverage),
            "vendors": len(vendors_without_coverage),
        }
        top_gap_domains = [
            domain
            for domain, gap_count in sorted(domain_gap_counts.items(), key=lambda item: item[1], reverse=True)
            if gap_count > 0
        ][:2]

        return {
            "job_id": job.id,
            "generated_at": now,
            "import_source": job.source_tool,
            "import_job_status": job.status,
            "import_job_updated_at": job_updated_at,
            "data_age_hours": data_age_hours,
            "stale": stale,
            "stale_reason": stale_reason,
            "context_flags": context_flags,
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
                "obligations_total": obligations_total,
                "obligation_gap_count": len(obligations_without_coverage),
                "obligation_coverage_pct": _coverage_pct(obligations_total, len(obligations_without_coverage)),
                "controls_total": controls_total,
                "control_gap_count": len(controls_without_coverage),
                "control_coverage_pct": _coverage_pct(controls_total, len(controls_without_coverage)),
                "ai_systems_total": ai_systems_total,
                "ai_system_gap_count": len(ai_systems_without_coverage),
                "ai_system_coverage_pct": _coverage_pct(ai_systems_total, len(ai_systems_without_coverage)),
                "vendors_total": vendors_total,
                "vendor_gap_count": len(vendors_without_coverage),
                "vendor_coverage_pct": _coverage_pct(vendors_total, len(vendors_without_coverage)),
                "top_gap_domains": top_gap_domains,
            },
        }
