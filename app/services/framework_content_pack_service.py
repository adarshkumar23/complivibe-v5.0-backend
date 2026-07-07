from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.framework import Framework
from app.models.framework_content_import import FrameworkContentImport
from app.models.framework_pack_coverage_report import FrameworkPackCoverageReport
from app.models.framework_section import FrameworkSection
from app.models.framework_version import FrameworkVersion
from app.models.obligation import Obligation
from app.models.obligation_applicability_question import ObligationApplicabilityQuestion
from app.models.obligation_content_version import ObligationContentVersion
from app.models.obligation_control_suggestion import ObligationControlSuggestion
from app.models.obligation_evidence_requirement import ObligationEvidenceRequirement
from app.services.framework_content_service import FrameworkContentService
from app.services.seed_service import OBLIGATION_SEEDS

PACK_CAVEAT = (
    "This framework content pack is a structured starter representation and does not constitute legal advice "
    "or complete regulatory coverage."
)
COVERAGE_CAVEAT = (
    "Coverage values reflect CompliVibe content metadata only and do not represent legal completeness or "
    "regulatory approval."
)
_ALLOWED_COVERAGE_LEVELS = {"metadata_only", "starter", "partial", "reviewed", "full_verified"}
_ALLOWED_REVIEW_STATUSES = {"unreviewed", "internal_review", "expert_reviewed", "full_verified"}
_SEED_PACK_MATCH_FIELDS = ("title", "description", "plain_language_summary", "obligation_type")


class FrameworkContentPackService:
    PACK_ROOT = Path(__file__).resolve().parent.parent / "content_packs" / "frameworks"

    def __init__(self, db: Session) -> None:
        self.db = db
        self.content_service = FrameworkContentService(db)

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)

    def _pack_file(self, pack_key: str) -> Path:
        return self.PACK_ROOT / f"{pack_key}.json"

    def list_packs(self) -> list[dict[str, Any]]:
        packs: list[dict[str, Any]] = []
        if not self.PACK_ROOT.exists():
            return packs
        for path in sorted(self.PACK_ROOT.glob("*.json")):
            payload = json.loads(path.read_text())
            packs.append(
                {
                    "pack_key": payload.get("pack_key", path.stem),
                    "framework_code": payload.get("framework_code", ""),
                    "framework_name": payload.get("framework_name", ""),
                    "version_label": payload.get("version_label", ""),
                    "coverage_level": payload.get("coverage_level", "metadata_only"),
                    "review_status": payload.get("review_status", "unreviewed"),
                    "caveat": payload.get("caveat", PACK_CAVEAT),
                    "source_reference": payload.get("source_reference"),
                    "source_url": payload.get("source_url"),
                }
            )
        return packs

    def load_pack(self, pack_key: str) -> dict[str, Any]:
        path = self._pack_file(pack_key)
        if not path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content pack not found")
        return json.loads(path.read_text())

    def validate_pack(self, pack_key: str) -> dict[str, Any]:
        payload = self.load_pack(pack_key)
        errors: list[str] = []
        warnings: list[str] = []

        required_fields = [
            "pack_key",
            "framework_code",
            "framework_name",
            "version_label",
            "coverage_level",
            "review_status",
            "caveat",
        ]
        for field in required_fields:
            if field not in payload:
                errors.append(f"{field} is required")

        if payload.get("coverage_level") not in _ALLOWED_COVERAGE_LEVELS:
            errors.append("coverage_level is invalid")
        if payload.get("review_status") not in _ALLOWED_REVIEW_STATUSES:
            errors.append("review_status is invalid")

        if payload.get("coverage_level") == "full_verified":
            errors.append("full_verified coverage level is not allowed for local starter/partial packs in this phase")

        caveat = str(payload.get("caveat", "")).strip()
        if caveat != PACK_CAVEAT:
            warnings.append("pack caveat should match required starter-pack caveat text")

        import_payload = {
            "sections": payload.get("sections", []) or [],
            "obligations": payload.get("obligations", []) or [],
            "content_versions": payload.get("content_versions", []) or [],
            "evidence_requirements": payload.get("evidence_requirements", []) or [],
            "control_suggestions": payload.get("control_suggestions", []) or [],
            "applicability_questions": payload.get("applicability_questions", []) or [],
        }

        framework = self.db.execute(
            select(Framework).where(Framework.code == payload.get("framework_code"))
        ).scalar_one_or_none()
        counts = {
            "sections": len(import_payload["sections"]),
            "obligations": len(import_payload["obligations"]),
            "content_versions": len(import_payload["content_versions"]),
            "evidence_requirements": len(import_payload["evidence_requirements"]),
            "control_suggestions": len(import_payload["control_suggestions"]),
            "applicability_questions": len(import_payload["applicability_questions"]),
        }
        if framework is None:
            errors.append("framework_code does not match a seeded framework")
        else:
            drift_rows = self._seed_pack_drift_rows(payload)
            for row in drift_rows:
                errors.append(
                    f"seed/pack drift for {row['framework_code']}:{row['reference_code']} on fields {', '.join(row['fields'])}"
                )
            import_counts, import_errors = self.content_service.validate_import_payload(
                framework_id=framework.id,
                payload_json=import_payload,
            )
            counts = import_counts
            errors.extend(import_errors)

        return {
            "valid": len(errors) == 0,
            "pack_key": payload.get("pack_key", pack_key),
            "framework_code": payload.get("framework_code"),
            "framework_name": payload.get("framework_name"),
            "coverage_level": payload.get("coverage_level"),
            "review_status": payload.get("review_status"),
            "caveat": payload.get("caveat", PACK_CAVEAT),
            "counts": counts,
            "validation_errors": errors,
            "warnings": warnings,
            "payload": payload,
            "import_payload": import_payload,
            "framework": framework,
        }

    @staticmethod
    def _seed_obligation_lookup() -> dict[tuple[str, str], dict[str, Any]]:
        return {(str(item["framework_code"]), str(item["reference_code"])): item for item in OBLIGATION_SEEDS}

    def _seed_pack_drift_rows(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        framework_code = str(payload.get("framework_code") or "")
        rows: list[dict[str, Any]] = []
        seed_lookup = self._seed_obligation_lookup()
        for item in payload.get("obligations", []) or []:
            reference_code = str(item.get("reference_code") or "")
            if not reference_code:
                continue
            seed = seed_lookup.get((framework_code, reference_code))
            if seed is None:
                continue
            drift_fields: list[str] = []
            for field in _SEED_PACK_MATCH_FIELDS:
                pack_value = str(item.get(field) or "").strip()
                seed_value = str(seed.get(field) or "").strip()
                if pack_value != seed_value:
                    drift_fields.append(field)
            if drift_fields:
                rows.append(
                    {
                        "framework_code": framework_code,
                        "reference_code": reference_code,
                        "fields": drift_fields,
                    }
                )
        return rows

    def consistency_check(self, *, pack_key: str | None = None) -> dict[str, Any]:
        pack_keys: list[str]
        if pack_key:
            pack_keys = [pack_key]
        else:
            pack_keys = sorted(path.stem for path in self.PACK_ROOT.glob("*.json"))
        drift_rows: list[dict[str, Any]] = []
        checked = 0
        for key in pack_keys:
            payload = self.load_pack(key)
            checked += 1
            for row in self._seed_pack_drift_rows(payload):
                drift_rows.append({"pack_key": key, **row})
        return {
            "pack_count_checked": checked,
            "drift_count": len(drift_rows),
            "drift_rows": drift_rows,
            "ok": len(drift_rows) == 0,
        }

    def apply_pack(
        self,
        *,
        pack_key: str,
        actor_user_id: uuid.UUID,
        organization_id: uuid.UUID,
        dry_run: bool,
        force_update: bool,
    ) -> dict[str, Any]:
        _ = force_update  # kept for explicit API contract; future diff-aware upsert handling.
        validation = self.validate_pack(pack_key)
        if not validation["valid"]:
            return {
                "valid": False,
                "pack_key": validation["pack_key"],
                "framework_code": validation["framework_code"],
                "framework_name": validation["framework_name"],
                "coverage_level": validation["coverage_level"],
                "review_status": validation["review_status"],
                "caveat": validation["caveat"],
                "counts": validation["counts"],
                "validation_errors": validation["validation_errors"],
                "warnings": validation["warnings"],
                "persisted": False,
            }

        if dry_run:
            return {
                "valid": True,
                "pack_key": validation["pack_key"],
                "framework_code": validation["framework_code"],
                "framework_name": validation["framework_name"],
                "coverage_level": validation["coverage_level"],
                "review_status": validation["review_status"],
                "caveat": validation["caveat"],
                "counts": validation["counts"],
                "validation_errors": [],
                "warnings": validation["warnings"],
                "persisted": False,
            }

        framework: Framework = validation["framework"]
        payload: dict[str, Any] = validation["payload"]
        import_payload: dict[str, Any] = validation["import_payload"]

        import_row = self.content_service.apply_import(
            framework_id=framework.id,
            organization_id=organization_id,
            import_type=str(payload.get("import_type") or "local_content_pack"),
            coverage_level=str(payload.get("coverage_level") or "starter"),
            source_name=str(payload.get("source_name") or "local_content_pack"),
            source_reference=str(payload.get("source_reference") or payload.get("pack_key") or pack_key),
            payload_json=import_payload,
            imported_by_user_id=actor_user_id,
        )

        # Align framework version coverage metadata if active version exists.
        active_version = self.db.execute(
            select(FrameworkVersion).where(
                FrameworkVersion.framework_id == framework.id,
                FrameworkVersion.status == "active",
            ).order_by(FrameworkVersion.created_at.desc())
        ).scalars().first()
        if active_version is not None and active_version.coverage_level != payload.get("coverage_level"):
            active_version.coverage_level = str(payload.get("coverage_level"))

        return {
            "valid": True,
            "pack_key": validation["pack_key"],
            "framework_code": validation["framework_code"],
            "framework_name": validation["framework_name"],
            "coverage_level": validation["coverage_level"],
            "review_status": validation["review_status"],
            "caveat": validation["caveat"],
            "counts": validation["counts"],
            "validation_errors": [],
            "warnings": validation["warnings"],
            "persisted": True,
            "import_id": str(import_row.id),
        }

    def _latest_review_status(self, framework_id: uuid.UUID) -> str:
        row = self.db.execute(
            select(ObligationContentVersion.review_status, func.count(ObligationContentVersion.id).label("cnt"))
            .join(Obligation, Obligation.id == ObligationContentVersion.obligation_id)
            .where(Obligation.framework_id == framework_id)
            .group_by(ObligationContentVersion.review_status)
            .order_by(func.count(ObligationContentVersion.id).desc())
        ).first()
        return str(row[0]) if row else "unreviewed"

    def coverage_details(self, framework_id: uuid.UUID) -> dict[str, Any]:
        framework = self.db.execute(select(Framework).where(Framework.id == framework_id)).scalar_one_or_none()
        if framework is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework not found")

        active_version = self.db.execute(
            select(FrameworkVersion).where(
                FrameworkVersion.framework_id == framework_id,
                FrameworkVersion.status == "active",
            ).order_by(FrameworkVersion.created_at.desc())
        ).scalars().first()

        sections = self.db.execute(
            select(FrameworkSection).where(FrameworkSection.framework_id == framework_id)
        ).scalars().all()
        obligations = self.db.execute(
            select(Obligation).where(Obligation.framework_id == framework_id)
        ).scalars().all()

        obligation_ids = [row.id for row in obligations]
        total_sections = len(sections)
        total_obligations = len(obligations)

        if obligation_ids:
            with_content_ids = set(
                self.db.execute(
                    select(ObligationContentVersion.obligation_id)
                    .where(ObligationContentVersion.obligation_id.in_(obligation_ids))
                    .group_by(ObligationContentVersion.obligation_id)
                ).scalars().all()
            )
            with_question_ids = set(
                self.db.execute(
                    select(ObligationApplicabilityQuestion.obligation_id)
                    .where(
                        ObligationApplicabilityQuestion.framework_id == framework_id,
                        ObligationApplicabilityQuestion.obligation_id.is_not(None),
                        ObligationApplicabilityQuestion.status == "active",
                    )
                    .group_by(ObligationApplicabilityQuestion.obligation_id)
                ).scalars().all()
            )
            with_evidence_ids = set(
                self.db.execute(
                    select(ObligationEvidenceRequirement.obligation_id)
                    .where(
                        ObligationEvidenceRequirement.framework_id == framework_id,
                        ObligationEvidenceRequirement.status == "active",
                    )
                    .group_by(ObligationEvidenceRequirement.obligation_id)
                ).scalars().all()
            )
            with_suggestion_ids = set(
                self.db.execute(
                    select(ObligationControlSuggestion.obligation_id)
                    .where(
                        ObligationControlSuggestion.framework_id == framework_id,
                        ObligationControlSuggestion.status == "active",
                    )
                    .group_by(ObligationControlSuggestion.obligation_id)
                ).scalars().all()
            )
        else:
            with_content_ids = set()
            with_question_ids = set()
            with_evidence_ids = set()
            with_suggestion_ids = set()

        obligation_by_id = {str(row.id): row for row in obligations}

        def _obligation_min(row: Obligation) -> dict[str, Any]:
            return {"id": str(row.id), "reference_code": row.reference_code, "title": row.title}

        missing_content = [_obligation_min(obligation_by_id[str(oid)]) for oid in obligation_by_id if uuid.UUID(oid) not in with_content_ids]
        missing_questions = [_obligation_min(obligation_by_id[str(oid)]) for oid in obligation_by_id if uuid.UUID(oid) not in with_question_ids]
        missing_evidence = [_obligation_min(obligation_by_id[str(oid)]) for oid in obligation_by_id if uuid.UUID(oid) not in with_evidence_ids]
        missing_suggestions = [_obligation_min(obligation_by_id[str(oid)]) for oid in obligation_by_id if uuid.UUID(oid) not in with_suggestion_ids]

        section_ids_with_obligations = {row.framework_section_id for row in obligations if row.framework_section_id is not None}
        sections_without_obligations = [
            {"id": str(row.id), "section_code": row.section_code, "title": row.title}
            for row in sections
            if row.id not in section_ids_with_obligations
        ]
        obligations_without_sections = [_obligation_min(row) for row in obligations if row.framework_section_id is None]

        with_content = len(with_content_ids)
        with_questions = len(with_question_ids)
        with_evidence = len(with_evidence_ids)
        with_suggestions = len(with_suggestion_ids)

        denominator = max(1, total_obligations * 4)
        coverage_percent_estimate = round(((with_content + with_questions + with_evidence + with_suggestions) / denominator) * 100, 2)

        coverage_level = active_version.coverage_level if active_version else framework.coverage_level
        review_status = self._latest_review_status(framework_id)

        return {
            "framework_id": framework_id,
            "framework_code": framework.code,
            "framework_name": framework.name,
            "framework_version_id": active_version.id if active_version else None,
            "active_version": active_version.version_label if active_version else None,
            "pack_key": f"{framework.code.lower()}_pack",
            "coverage_level": coverage_level,
            "review_status": review_status,
            "total_sections": total_sections,
            "total_obligations": total_obligations,
            "obligations_with_content": with_content,
            "obligations_with_questions": with_questions,
            "obligations_with_evidence_requirements": with_evidence,
            "obligations_with_control_suggestions": with_suggestions,
            "missing_content_count": len(missing_content),
            "missing_question_count": len(missing_questions),
            "missing_evidence_requirement_count": len(missing_evidence),
            "missing_control_suggestion_count": len(missing_suggestions),
            "coverage_percent_estimate": coverage_percent_estimate,
            "obligations_missing_content": missing_content,
            "obligations_missing_applicability_questions": missing_questions,
            "obligations_missing_evidence_requirements": missing_evidence,
            "obligations_missing_control_suggestions": missing_suggestions,
            "sections_without_obligations": sections_without_obligations,
            "obligations_without_sections": obligations_without_sections,
            "generated_at": self.now(),
            "caveat": COVERAGE_CAVEAT,
        }

    def create_coverage_report(
        self,
        *,
        framework_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> FrameworkPackCoverageReport:
        details = self.coverage_details(framework_id)
        report = FrameworkPackCoverageReport(
            framework_id=framework_id,
            framework_version_id=details["framework_version_id"],
            pack_key=details["pack_key"],
            coverage_level=details["coverage_level"],
            review_status=details["review_status"],
            total_sections=details["total_sections"],
            total_obligations=details["total_obligations"],
            obligations_with_content=details["obligations_with_content"],
            obligations_with_questions=details["obligations_with_questions"],
            obligations_with_evidence_requirements=details["obligations_with_evidence_requirements"],
            obligations_with_control_suggestions=details["obligations_with_control_suggestions"],
            missing_content_count=details["missing_content_count"],
            missing_question_count=details["missing_question_count"],
            missing_evidence_requirement_count=details["missing_evidence_requirement_count"],
            missing_control_suggestion_count=details["missing_control_suggestion_count"],
            report_json={
                "gaps": {
                    "obligations_missing_content": details["obligations_missing_content"],
                    "obligations_missing_applicability_questions": details["obligations_missing_applicability_questions"],
                    "obligations_missing_evidence_requirements": details["obligations_missing_evidence_requirements"],
                    "obligations_missing_control_suggestions": details["obligations_missing_control_suggestions"],
                    "sections_without_obligations": details["sections_without_obligations"],
                    "obligations_without_sections": details["obligations_without_sections"],
                },
                "coverage_percent_estimate": details["coverage_percent_estimate"],
                "caveat": COVERAGE_CAVEAT,
            },
            generated_at=details["generated_at"],
            created_by_user_id=actor_user_id,
        )
        self.db.add(report)
        self.db.flush()
        return report

    def list_coverage_reports(self, framework_id: uuid.UUID) -> list[FrameworkPackCoverageReport]:
        return self.db.execute(
            select(FrameworkPackCoverageReport)
            .where(FrameworkPackCoverageReport.framework_id == framework_id)
            .order_by(FrameworkPackCoverageReport.generated_at.desc())
        ).scalars().all()

    def global_coverage_summary(self) -> list[dict[str, Any]]:
        frameworks = self.db.execute(select(Framework).order_by(Framework.name.asc())).scalars().all()
        results: list[dict[str, Any]] = []
        for framework in frameworks:
            details = self.coverage_details(framework.id)
            results.append(
                {
                    "framework_id": framework.id,
                    "framework_code": framework.code,
                    "framework_name": framework.name,
                    "active_version": details["active_version"],
                    "coverage_level": details["coverage_level"],
                    "review_status": details["review_status"],
                    "total_sections": details["total_sections"],
                    "total_obligations": details["total_obligations"],
                    "coverage_percent_estimate": details["coverage_percent_estimate"],
                    "caveat": COVERAGE_CAVEAT,
                }
            )
        return results

    def latest_import_for_framework(self, framework_id: uuid.UUID) -> FrameworkContentImport | None:
        return self.db.execute(
            select(FrameworkContentImport)
            .where(FrameworkContentImport.framework_id == framework_id)
            .order_by(FrameworkContentImport.created_at.desc())
        ).scalars().first()
