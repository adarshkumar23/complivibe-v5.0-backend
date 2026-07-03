import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.framework import Framework
from app.models.framework_content_import import FrameworkContentImport
from app.models.framework_section import FrameworkSection
from app.models.framework_version import FrameworkVersion
from app.models.obligation import Obligation
from app.models.obligation_applicability_question import ObligationApplicabilityQuestion
from app.models.obligation_content_version import ObligationContentVersion
from app.models.obligation_control_suggestion import ObligationControlSuggestion
from app.models.obligation_evidence_requirement import ObligationEvidenceRequirement
from app.core.validation import validate_choice

FRAMEWORK_COVERAGE_LEVELS = {"metadata_only", "starter", "partial", "reviewed", "full_verified"}
FRAMEWORK_VERSION_STATUSES = {"draft", "active", "superseded", "archived"}
FRAMEWORK_SECTION_STATUSES = {"active", "inactive", "archived"}
QUESTION_ANSWER_TYPES = {"boolean", "single_select", "multi_select", "text", "number", "date"}
QUESTION_STATUSES = {"active", "inactive", "archived"}
REVIEW_STATUSES = {"unreviewed", "internal_review", "expert_reviewed", "customer_verified", "superseded"}
EVIDENCE_TYPES = {
    "policy_document",
    "screenshot",
    "system_export",
    "attestation",
    "audit_report",
    "risk_assessment",
    "meeting_record",
    "configuration_snapshot",
    "training_record",
    "vendor_document",
    "ai_model_documentation",
    "other",
}
PRIORITIES = {"low", "normal", "high", "critical"}
ACTIVE_REVIEWED_STATUSES = {"internal_review", "expert_reviewed", "customer_verified"}


class FrameworkContentService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def validate_coverage_level(coverage_level: str) -> None:
        coverage_level = validate_choice(coverage_level, FRAMEWORK_COVERAGE_LEVELS, "coverage_level", status_code=status.HTTP_400_BAD_REQUEST)
    @staticmethod
    def validate_version_status(status_value: str) -> None:
        status_value = validate_choice(status_value, FRAMEWORK_VERSION_STATUSES, "framework version status", status_code=status.HTTP_400_BAD_REQUEST)
    @staticmethod
    def validate_section_status(status_value: str) -> None:
        status_value = validate_choice(status_value, FRAMEWORK_SECTION_STATUSES, "section status", status_code=status.HTTP_400_BAD_REQUEST)
    @staticmethod
    def validate_answer_type(answer_type: str) -> None:
        answer_type = validate_choice(answer_type, QUESTION_ANSWER_TYPES, "answer_type", status_code=status.HTTP_400_BAD_REQUEST)
    @staticmethod
    def validate_review_status(review_status: str) -> None:
        review_status = validate_choice(review_status, REVIEW_STATUSES, "review_status", status_code=status.HTTP_400_BAD_REQUEST)
    @staticmethod
    def validate_evidence_type(evidence_type: str) -> None:
        evidence_type = validate_choice(evidence_type, EVIDENCE_TYPES, "evidence_type", status_code=status.HTTP_400_BAD_REQUEST)
    @staticmethod
    def validate_priority(priority: str) -> None:
        priority = validate_choice(priority, PRIORITIES, "priority", status_code=status.HTTP_400_BAD_REQUEST)
    def require_framework(self, framework_id: uuid.UUID) -> Framework:
        row = self.db.execute(select(Framework).where(Framework.id == framework_id)).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework not found")
        return row

    def list_versions(self, framework_id: uuid.UUID) -> list[FrameworkVersion]:
        return self.db.execute(
            select(FrameworkVersion)
            .where(FrameworkVersion.framework_id == framework_id)
            .order_by(FrameworkVersion.effective_from.desc().nullslast(), FrameworkVersion.created_at.desc())
        ).scalars().all()

    def create_version(
        self,
        *,
        framework_id: uuid.UUID,
        version_label: str,
        source_url: str | None,
        source_reference: str | None,
        effective_from,
        effective_until,
        status_value: str,
        coverage_level: str,
        notes: str | None,
    ) -> FrameworkVersion:
        self.validate_version_status(status_value)
        self.validate_coverage_level(coverage_level)

        row = FrameworkVersion(
            framework_id=framework_id,
            version_label=version_label,
            source_url=source_url,
            source_reference=source_reference,
            effective_from=effective_from,
            effective_until=effective_until,
            status=status_value,
            coverage_level=coverage_level,
            notes=notes,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_sections(self, framework_id: uuid.UUID) -> list[FrameworkSection]:
        return self.db.execute(
            select(FrameworkSection)
            .where(FrameworkSection.framework_id == framework_id)
            .order_by(FrameworkSection.sort_order.asc(), FrameworkSection.section_code.asc())
        ).scalars().all()

    def create_section(
        self,
        *,
        framework_id: uuid.UUID,
        framework_version_id: uuid.UUID | None,
        parent_section_id: uuid.UUID | None,
        section_code: str,
        title: str,
        description: str | None,
        sort_order: int,
        status_value: str,
        metadata_json: dict | None,
    ) -> FrameworkSection:
        self.validate_section_status(status_value)

        if framework_version_id is not None:
            version = self.db.execute(select(FrameworkVersion).where(FrameworkVersion.id == framework_version_id)).scalar_one_or_none()
            if version is None or version.framework_id != framework_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid framework_version_id")

        if parent_section_id is not None:
            parent = self.db.execute(select(FrameworkSection).where(FrameworkSection.id == parent_section_id)).scalar_one_or_none()
            if parent is None or parent.framework_id != framework_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid parent_section_id")

        existing = self.db.execute(
            select(FrameworkSection).where(
                FrameworkSection.framework_id == framework_id,
                FrameworkSection.framework_version_id == framework_version_id,
                FrameworkSection.section_code == section_code,
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="section_code already exists in this framework/version")

        row = FrameworkSection(
            framework_id=framework_id,
            framework_version_id=framework_version_id,
            parent_section_id=parent_section_id,
            section_code=section_code,
            title=title,
            description=description,
            sort_order=sort_order,
            status=status_value,
            metadata_json=metadata_json,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def latest_content_version(self, obligation_id: uuid.UUID) -> ObligationContentVersion | None:
        return self.db.execute(
            select(ObligationContentVersion)
            .where(ObligationContentVersion.obligation_id == obligation_id)
            .order_by(ObligationContentVersion.created_at.desc())
        ).scalars().first()

    def content_summary(self, framework_id: uuid.UUID) -> dict:
        active_version = self.db.execute(
            select(FrameworkVersion).where(
                FrameworkVersion.framework_id == framework_id,
                FrameworkVersion.status == "active",
            ).order_by(FrameworkVersion.created_at.desc())
        ).scalars().first()

        total_sections = int(self.db.execute(select(func.count(FrameworkSection.id)).where(FrameworkSection.framework_id == framework_id)).scalar_one())
        total_obligations = int(self.db.execute(select(func.count(Obligation.id)).where(Obligation.framework_id == framework_id)).scalar_one())

        obligations_with_content_versions = int(
            self.db.execute(
                select(func.count(func.distinct(ObligationContentVersion.obligation_id)))
                .join(Obligation, Obligation.id == ObligationContentVersion.obligation_id)
                .where(Obligation.framework_id == framework_id)
            ).scalar_one()
        )
        obligations_with_evidence_requirements = int(
            self.db.execute(
                select(func.count(func.distinct(ObligationEvidenceRequirement.obligation_id)))
                .join(Obligation, Obligation.id == ObligationEvidenceRequirement.obligation_id)
                .where(Obligation.framework_id == framework_id)
            ).scalar_one()
        )
        obligations_with_control_suggestions = int(
            self.db.execute(
                select(func.count(func.distinct(ObligationControlSuggestion.obligation_id)))
                .join(Obligation, Obligation.id == ObligationControlSuggestion.obligation_id)
                .where(Obligation.framework_id == framework_id)
            ).scalar_one()
        )
        applicability_questions = int(
            self.db.execute(
                select(func.count(ObligationApplicabilityQuestion.id)).where(ObligationApplicabilityQuestion.framework_id == framework_id)
            ).scalar_one()
        )

        reviewed_obligations = int(
            self.db.execute(
                select(func.count(func.distinct(ObligationContentVersion.obligation_id)))
                .join(Obligation, Obligation.id == ObligationContentVersion.obligation_id)
                .where(
                    Obligation.framework_id == framework_id,
                    ObligationContentVersion.review_status.in_(list(ACTIVE_REVIEWED_STATUSES)),
                )
            ).scalar_one()
        )

        return {
            "framework_id": framework_id,
            "active_version": active_version.version_label if active_version else None,
            "coverage_level": active_version.coverage_level if active_version else "metadata_only",
            "total_sections": total_sections,
            "total_obligations": total_obligations,
            "obligations_with_content_versions": obligations_with_content_versions,
            "obligations_with_evidence_requirements": obligations_with_evidence_requirements,
            "obligations_with_control_suggestions": obligations_with_control_suggestions,
            "applicability_questions": applicability_questions,
            "reviewed_obligations": reviewed_obligations,
            "unreviewed_obligations": max(0, total_obligations - reviewed_obligations),
        }

    def validate_import_payload(self, *, framework_id: uuid.UUID, payload_json: dict) -> tuple[dict, list[str]]:
        counts = {
            "sections": len(payload_json.get("sections", []) or []),
            "obligations": len(payload_json.get("obligations", []) or []),
            "content_versions": len(payload_json.get("content_versions", []) or []),
            "evidence_requirements": len(payload_json.get("evidence_requirements", []) or []),
            "control_suggestions": len(payload_json.get("control_suggestions", []) or []),
            "applicability_questions": len(payload_json.get("applicability_questions", []) or []),
        }
        errors: list[str] = []

        if not isinstance(payload_json, dict):
            return counts, ["payload_json must be an object"]

        for section in payload_json.get("sections", []) or []:
            if not section.get("section_code"):
                errors.append("section.section_code is required")
            if not section.get("title"):
                errors.append("section.title is required")

        valid_obligation_ids: set[str] = set()
        valid_reference_codes: set[str] = set()
        for obligation in payload_json.get("obligations", []) or []:
            if not obligation.get("reference_code"):
                errors.append("obligation.reference_code is required")
            if not obligation.get("title"):
                errors.append("obligation.title is required")
            if obligation.get("reference_code"):
                valid_reference_codes.add(str(obligation["reference_code"]))
            if obligation.get("id"):
                valid_obligation_ids.add(str(obligation["id"]))

        def _has_obligation_pointer(item: dict) -> bool:
            if item.get("obligation_id"):
                return str(item.get("obligation_id")) in valid_obligation_ids or self.db.execute(
                    select(func.count(Obligation.id)).where(
                        Obligation.framework_id == framework_id,
                        Obligation.id == uuid.UUID(str(item.get("obligation_id"))),
                    )
                ).scalar_one() > 0
            ref_code = item.get("reference_code")
            if ref_code:
                return ref_code in valid_reference_codes or self.db.execute(
                    select(func.count(Obligation.id)).where(
                        Obligation.framework_id == framework_id,
                        Obligation.reference_code == ref_code,
                    )
                ).scalar_one() > 0
            return False

        for item in payload_json.get("content_versions", []) or []:
            if not _has_obligation_pointer(item):
                errors.append("content_version must reference a valid obligation (obligation_id or reference_code)")
            if not item.get("version_label"):
                errors.append("content_version.version_label is required")
            if not item.get("obligation_text"):
                errors.append("content_version.obligation_text is required")

        for item in payload_json.get("evidence_requirements", []) or []:
            if not _has_obligation_pointer(item):
                errors.append("evidence_requirement must reference a valid obligation")
            if not item.get("requirement_key"):
                errors.append("evidence_requirement.requirement_key is required")
            if item.get("evidence_type") and item.get("evidence_type") not in EVIDENCE_TYPES:
                errors.append("evidence_requirement.evidence_type is invalid")

        for item in payload_json.get("control_suggestions", []) or []:
            if not _has_obligation_pointer(item):
                errors.append("control_suggestion must reference a valid obligation")
            if not item.get("control_title"):
                errors.append("control_suggestion.control_title is required")

        for item in payload_json.get("applicability_questions", []) or []:
            answer_type = item.get("answer_type")
            if not item.get("question_key"):
                errors.append("applicability_question.question_key is required")
            if not item.get("question_text"):
                errors.append("applicability_question.question_text is required")
            if answer_type and answer_type not in QUESTION_ANSWER_TYPES:
                errors.append("applicability_question.answer_type is invalid")

        return counts, errors

    def _resolve_obligation(
        self,
        *,
        framework_id: uuid.UUID,
        obligation_id: str | None,
        reference_code: str | None,
    ) -> Obligation | None:
        if obligation_id:
            try:
                oid = uuid.UUID(str(obligation_id))
            except ValueError:
                return None
            return self.db.execute(
                select(Obligation).where(
                    Obligation.framework_id == framework_id,
                    Obligation.id == oid,
                )
            ).scalar_one_or_none()
        if reference_code:
            return self.db.execute(
                select(Obligation).where(
                    Obligation.framework_id == framework_id,
                    Obligation.reference_code == reference_code,
                )
            ).scalar_one_or_none()
        return None

    def apply_import(
        self,
        *,
        framework_id: uuid.UUID,
        organization_id: uuid.UUID | None,
        import_type: str,
        coverage_level: str,
        source_name: str | None,
        source_reference: str | None,
        payload_json: dict,
        imported_by_user_id: uuid.UUID,
    ) -> FrameworkContentImport:
        self.validate_coverage_level(coverage_level)

        counts, errors = self.validate_import_payload(framework_id=framework_id, payload_json=payload_json)
        if errors:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"validation_errors": errors, "counts": counts})

        now = self.now()
        import_row = FrameworkContentImport(
            organization_id=organization_id,
            framework_id=framework_id,
            import_type=import_type,
            status="processing",
            source_name=source_name,
            source_reference=source_reference,
            coverage_level=coverage_level,
            imported_by_user_id=imported_by_user_id,
            started_at=now,
        )
        self.db.add(import_row)
        self.db.flush()

        # Sections upsert by section_code + framework_version_id
        for item in payload_json.get("sections", []) or []:
            framework_version_id = item.get("framework_version_id")
            existing = self.db.execute(
                select(FrameworkSection).where(
                    FrameworkSection.framework_id == framework_id,
                    FrameworkSection.framework_version_id == framework_version_id,
                    FrameworkSection.section_code == item["section_code"],
                )
            ).scalar_one_or_none()
            if existing is None:
                self.db.add(
                    FrameworkSection(
                        framework_id=framework_id,
                        framework_version_id=framework_version_id,
                        parent_section_id=item.get("parent_section_id"),
                        section_code=item["section_code"],
                        title=item["title"],
                        description=item.get("description"),
                        sort_order=item.get("sort_order", 0),
                        status=item.get("status", "active"),
                        metadata_json=item.get("metadata_json"),
                    )
                )
            else:
                existing.title = item.get("title", existing.title)
                existing.description = item.get("description", existing.description)
                existing.sort_order = item.get("sort_order", existing.sort_order)
                existing.status = item.get("status", existing.status)
                existing.metadata_json = item.get("metadata_json", existing.metadata_json)

        self.db.flush()

        # Obligations upsert by reference_code
        for item in payload_json.get("obligations", []) or []:
            framework_section_id = item.get("framework_section_id")
            if framework_section_id is None and item.get("section_code"):
                section = self.db.execute(
                    select(FrameworkSection).where(
                        FrameworkSection.framework_id == framework_id,
                        FrameworkSection.section_code == item.get("section_code"),
                    )
                ).scalar_one_or_none()
                framework_section_id = section.id if section else None
            existing = self.db.execute(
                select(Obligation).where(
                    Obligation.framework_id == framework_id,
                    Obligation.reference_code == item["reference_code"],
                )
            ).scalar_one_or_none()
            if existing is None:
                self.db.add(
                    Obligation(
                        framework_id=framework_id,
                        framework_section_id=framework_section_id,
                        reference_code=item["reference_code"],
                        title=item["title"],
                        description=item.get("description"),
                        plain_language_summary=item.get("plain_language_summary"),
                        obligation_type=item.get("obligation_type"),
                        jurisdiction=item.get("jurisdiction", "Unknown"),
                        source_url=item.get("source_url"),
                        version=item.get("version"),
                        status=item.get("status", "active"),
                        effective_date=item.get("effective_date"),
                    )
                )
            else:
                if framework_section_id is not None:
                    existing.framework_section_id = framework_section_id
                existing.title = item.get("title", existing.title)
                existing.description = item.get("description", existing.description)
                existing.plain_language_summary = item.get("plain_language_summary", existing.plain_language_summary)
                existing.obligation_type = item.get("obligation_type", existing.obligation_type)
                existing.jurisdiction = item.get("jurisdiction", existing.jurisdiction)
                existing.source_url = item.get("source_url", existing.source_url)
                existing.version = item.get("version", existing.version)
                existing.status = item.get("status", existing.status)
                existing.effective_date = item.get("effective_date", existing.effective_date)

        self.db.flush()

        # Content versions upsert by obligation + version_label
        for item in payload_json.get("content_versions", []) or []:
            obligation = self._resolve_obligation(
                framework_id=framework_id,
                obligation_id=item.get("obligation_id"),
                reference_code=item.get("reference_code"),
            )
            if obligation is None:
                continue
            existing = self.db.execute(
                select(ObligationContentVersion).where(
                    ObligationContentVersion.obligation_id == obligation.id,
                    ObligationContentVersion.version_label == item["version_label"],
                )
            ).scalar_one_or_none()
            if existing is None:
                self.db.add(
                    ObligationContentVersion(
                        obligation_id=obligation.id,
                        version_label=item["version_label"],
                        obligation_text=item["obligation_text"],
                        normalized_summary=item.get("normalized_summary"),
                        source_reference=item.get("source_reference"),
                        source_url=item.get("source_url"),
                        effective_from=item.get("effective_from"),
                        effective_until=item.get("effective_until"),
                        coverage_level=item.get("coverage_level", coverage_level),
                        review_status=item.get("review_status", "unreviewed"),
                        metadata_json=item.get("metadata_json"),
                        created_at=self.now(),
                    )
                )

        # Evidence requirements upsert by obligation + requirement_key
        for item in payload_json.get("evidence_requirements", []) or []:
            obligation = self._resolve_obligation(
                framework_id=framework_id,
                obligation_id=item.get("obligation_id"),
                reference_code=item.get("reference_code"),
            )
            if obligation is None:
                continue
            existing = self.db.execute(
                select(ObligationEvidenceRequirement).where(
                    ObligationEvidenceRequirement.obligation_id == obligation.id,
                    ObligationEvidenceRequirement.requirement_key == item["requirement_key"],
                )
            ).scalar_one_or_none()
            if existing is None:
                self.db.add(
                    ObligationEvidenceRequirement(
                        framework_id=framework_id,
                        obligation_id=obligation.id,
                        requirement_key=item["requirement_key"],
                        title=item.get("title", item["requirement_key"]),
                        description=item.get("description"),
                        evidence_type=item.get("evidence_type", "other"),
                        required=item.get("required", False),
                        frequency=item.get("frequency"),
                        status=item.get("status", "active"),
                        metadata_json=item.get("metadata_json"),
                    )
                )

        # Control suggestions upsert by obligation + control_title
        for item in payload_json.get("control_suggestions", []) or []:
            obligation = self._resolve_obligation(
                framework_id=framework_id,
                obligation_id=item.get("obligation_id"),
                reference_code=item.get("reference_code"),
            )
            if obligation is None:
                continue
            existing = self.db.execute(
                select(ObligationControlSuggestion).where(
                    ObligationControlSuggestion.obligation_id == obligation.id,
                    ObligationControlSuggestion.control_title == item["control_title"],
                )
            ).scalar_one_or_none()
            if existing is None:
                self.db.add(
                    ObligationControlSuggestion(
                        framework_id=framework_id,
                        obligation_id=obligation.id,
                        control_title=item["control_title"],
                        control_description=item.get("control_description"),
                        control_domain=item.get("control_domain"),
                        control_type=item.get("control_type"),
                        priority=item.get("priority", "normal"),
                        status=item.get("status", "active"),
                        metadata_json=item.get("metadata_json"),
                    )
                )

        # Applicability questions upsert by framework + obligation + question_key + organization
        for item in payload_json.get("applicability_questions", []) or []:
            obligation = self._resolve_obligation(
                framework_id=framework_id,
                obligation_id=item.get("obligation_id"),
                reference_code=item.get("reference_code"),
            )
            obligation_id = obligation.id if obligation else item.get("obligation_id")
            question_org_id = item.get("organization_id")
            existing = self.db.execute(
                select(ObligationApplicabilityQuestion).where(
                    ObligationApplicabilityQuestion.framework_id == framework_id,
                    ObligationApplicabilityQuestion.organization_id == question_org_id,
                    ObligationApplicabilityQuestion.obligation_id == obligation_id,
                    ObligationApplicabilityQuestion.question_key == item["question_key"],
                )
            ).scalar_one_or_none()
            if existing is None:
                self.db.add(
                    ObligationApplicabilityQuestion(
                        organization_id=question_org_id,
                        framework_id=framework_id,
                        obligation_id=obligation_id,
                        question_key=item["question_key"],
                        question_text=item["question_text"],
                        help_text=item.get("help_text"),
                        answer_type=item.get("answer_type", "boolean"),
                        required=item.get("required", False),
                        sort_order=item.get("sort_order", 0),
                        status=item.get("status", "active"),
                        metadata_json=item.get("metadata_json"),
                    )
                )

        import_row.status = "completed"
        import_row.finished_at = self.now()
        import_row.summary_json = {"counts": counts, "validation_errors": []}
        self.db.flush()
        return import_row
