import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.applicability_evaluation_result import ApplicabilityEvaluationResult
from app.models.control import Control
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.framework import Framework
from app.models.obligation import Obligation
from app.models.obligation_control_recommendation import ObligationControlRecommendation
from app.models.obligation_control_suggestion import ObligationControlSuggestion
from app.models.organization_framework import OrganizationFramework
from app.models.organization_obligation_state import OrganizationObligationState
from app.models.recommendation_generation_run import RecommendationGenerationRun
from app.models.task import Task
from app.repositories.applicability_repository import ApplicabilityRepository
from app.repositories.control_recommendation_repository import ControlRecommendationRepository

CONTROL_RECOMMENDATION_CAVEAT = (
    "This recommendation is generated deterministically from CompliVibe records and configured framework content. "
    "It is not legal advice or a final compliance determination."
)


class ControlRecommendationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ControlRecommendationRepository(db)
        self.applicability_repo = ApplicabilityRepository(db)

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)

    def require_framework_active_for_org(self, *, organization_id: uuid.UUID, framework_id: uuid.UUID) -> Framework:
        framework = self.db.execute(select(Framework).where(Framework.id == framework_id)).scalar_one_or_none()
        if framework is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework not found")

        active = self.db.execute(
            select(OrganizationFramework).where(
                OrganizationFramework.organization_id == organization_id,
                OrganizationFramework.framework_id == framework_id,
                OrganizationFramework.status == "active",
            )
        ).scalar_one_or_none()
        if active is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Framework is not active for organization")
        return framework

    def _priority_to_control_criticality(self, priority: str) -> str:
        if priority == "critical":
            return "critical"
        if priority == "high":
            return "high"
        if priority == "low":
            return "low"
        return "medium"

    def _build_provenance(
        self,
        *,
        framework_id: uuid.UUID,
        obligation_id: uuid.UUID,
        obligation_state: OrganizationObligationState | None,
        latest_eval: ApplicabilityEvaluationResult | None,
        mapped_control_ids: list[uuid.UUID],
        evidence_ids: list[uuid.UUID],
        suggestion_id: uuid.UUID | None,
        rule_name: str,
    ) -> dict[str, Any]:
        return {
            "framework_id": str(framework_id),
            "obligation_id": str(obligation_id),
            "organization_obligation_state_id": str(obligation_state.id) if obligation_state else None,
            "latest_applicability_evaluation_result_id": str(latest_eval.id) if latest_eval else None,
            "mapped_control_ids": [str(value) for value in mapped_control_ids],
            "evidence_item_ids": [str(value) for value in evidence_ids],
            "suggestion_id": str(suggestion_id) if suggestion_id else None,
            "deterministic_rule": rule_name,
            "caveat": CONTROL_RECOMMENDATION_CAVEAT,
        }

    def _effective_applicability(
        self,
        *,
        organization_id: uuid.UUID,
        framework_id: uuid.UUID,
        obligation_id: uuid.UUID,
    ) -> tuple[str, OrganizationObligationState | None, ApplicabilityEvaluationResult | None]:
        state = self.db.execute(
            select(OrganizationObligationState).where(
                OrganizationObligationState.organization_id == organization_id,
                OrganizationObligationState.obligation_id == obligation_id,
            )
        ).scalar_one_or_none()

        latest = self.applicability_repo.latest_result_for_obligation(
            organization_id=organization_id,
            framework_id=framework_id,
            obligation_id=obligation_id,
        )

        if state is not None and state.applicability_status:
            return state.applicability_status, state, latest
        if latest is not None and latest.suggested_applicability:
            return latest.suggested_applicability, state, latest
        return "unknown", state, latest

    def _mapped_controls(
        self,
        *,
        organization_id: uuid.UUID,
        obligation_id: uuid.UUID,
    ) -> tuple[list[ControlObligationMapping], list[ControlObligationMapping], list[Control]]:
        all_mappings = self.db.execute(
            select(ControlObligationMapping).where(
                ControlObligationMapping.organization_id == organization_id,
                ControlObligationMapping.obligation_id == obligation_id,
            )
        ).scalars().all()

        active_mappings = [m for m in all_mappings if m.status == "active"]
        control_ids = [m.control_id for m in active_mappings]
        if not control_ids:
            return all_mappings, active_mappings, []

        controls = self.db.execute(
            select(Control).where(
                Control.organization_id == organization_id,
                Control.id.in_(control_ids),
            )
        ).scalars().all()
        active_controls = [c for c in controls if c.status != "archived"]
        return all_mappings, active_mappings, active_controls

    def _evidence_for_controls(self, *, organization_id: uuid.UUID, control_ids: list[uuid.UUID]) -> tuple[list[EvidenceItem], list[uuid.UUID]]:
        if not control_ids:
            return [], []

        links = self.db.execute(
            select(EvidenceControlLink).where(
                EvidenceControlLink.organization_id == organization_id,
                EvidenceControlLink.control_id.in_(control_ids),
                EvidenceControlLink.link_status == "active",
            )
        ).scalars().all()
        evidence_ids = list({link.evidence_item_id for link in links})
        if not evidence_ids:
            return [], []

        evidence_rows = self.db.execute(
            select(EvidenceItem).where(
                EvidenceItem.organization_id == organization_id,
                EvidenceItem.id.in_(evidence_ids),
                EvidenceItem.status != "archived",
            )
        ).scalars().all()
        return evidence_rows, evidence_ids

    def _find_active_suggestion(self, obligation_id: uuid.UUID) -> ObligationControlSuggestion | None:
        return self.db.execute(
            select(ObligationControlSuggestion)
            .where(
                ObligationControlSuggestion.obligation_id == obligation_id,
                ObligationControlSuggestion.status == "active",
            )
            .order_by(ObligationControlSuggestion.created_at.asc())
        ).scalars().first()

    def _candidate_recommendations(
        self,
        *,
        organization_id: uuid.UUID,
        framework_id: uuid.UUID,
        obligation: Obligation,
        include_non_applicable_review: bool,
    ) -> list[dict[str, Any]]:
        applicability, state, latest_eval = self._effective_applicability(
            organization_id=organization_id,
            framework_id=framework_id,
            obligation_id=obligation.id,
        )

        all_mappings, _active_mappings, active_controls = self._mapped_controls(
            organization_id=organization_id,
            obligation_id=obligation.id,
        )

        control_ids = [c.id for c in active_controls]
        evidence_rows, evidence_ids = self._evidence_for_controls(organization_id=organization_id, control_ids=control_ids)

        has_verified_current = any(
            item.review_status == "verified" and item.freshness_status in {"current", "expiring_soon"} for item in evidence_rows
        )
        has_expired_verified = any(
            item.review_status == "verified" and item.freshness_status == "expired" for item in evidence_rows
        )

        candidates: list[dict[str, Any]] = []

        if applicability == "not_applicable":
            if include_non_applicable_review and latest_eval and latest_eval.suggested_applicability == "needs_review":
                candidates.append(
                    {
                        "recommendation_type": "review_applicability",
                        "priority": "normal",
                        "status": "open",
                        "title": f"Review applicability: {obligation.reference_code}",
                        "rationale": "Obligation was marked not_applicable but latest evaluation indicates needs_review.",
                        "recommended_control_title": None,
                        "recommended_control_description": None,
                        "existing_control_id": None,
                        "suggestion_id": None,
                        "confidence_level": "needs_review",
                        "source": "applicability_evaluation",
                        "rule_name": "non_applicable_needs_review",
                    }
                )
            return candidates

        if applicability in {"needs_review", "unknown"}:
            candidates.append(
                {
                    "recommendation_type": "review_applicability",
                    "priority": "normal",
                    "status": "open",
                    "title": f"Review applicability: {obligation.reference_code}",
                    "rationale": "Applicability is needs_review/unknown based on deterministic evaluation context.",
                    "recommended_control_title": None,
                    "recommended_control_description": None,
                    "existing_control_id": None,
                    "suggestion_id": None,
                    "confidence_level": "needs_review",
                    "source": "applicability_evaluation",
                    "rule_name": "applicability_needs_review_or_unknown",
                }
            )
            return candidates

        if applicability != "applicable":
            return candidates

        suggestion = self._find_active_suggestion(obligation.id)

        if not active_controls:
            if all_mappings:
                candidates.append(
                    {
                        "recommendation_type": "review_existing_control",
                        "priority": "high",
                        "status": "open",
                        "title": f"Review existing controls for obligation {obligation.reference_code}",
                        "rationale": "Applicable obligation has mapped controls but none are currently active.",
                        "recommended_control_title": suggestion.control_title if suggestion else None,
                        "recommended_control_description": suggestion.control_description if suggestion else None,
                        "existing_control_id": None,
                        "suggestion_id": suggestion.id if suggestion else None,
                        "confidence_level": "deterministic_partial",
                        "source": "coverage_gap",
                        "rule_name": "applicable_obligation_only_inactive_or_archived_controls",
                    }
                )
            else:
                title = suggestion.control_title if suggestion else f"Control for {obligation.reference_code}"
                description = suggestion.control_description if suggestion else (
                    "Create a control to address this applicable obligation."
                )
                candidates.append(
                    {
                        "recommendation_type": "create_control",
                        "priority": "high",
                        "status": "open",
                        "title": f"Create control for obligation {obligation.reference_code}",
                        "rationale": "Applicable obligation has no active mapped controls.",
                        "recommended_control_title": title,
                        "recommended_control_description": description,
                        "existing_control_id": None,
                        "suggestion_id": suggestion.id if suggestion else None,
                        "confidence_level": "deterministic_exact" if suggestion else "needs_review",
                        "source": "coverage_gap",
                        "rule_name": "applicable_obligation_without_controls",
                    }
                )

            return [
                {
                    **candidate,
                    "provenance_json": self._build_provenance(
                        framework_id=framework_id,
                        obligation_id=obligation.id,
                        obligation_state=state,
                        latest_eval=latest_eval,
                        mapped_control_ids=control_ids,
                        evidence_ids=evidence_ids,
                        suggestion_id=candidate.get("suggestion_id"),
                        rule_name=candidate["rule_name"],
                    ),
                }
                for candidate in candidates
            ]

        existing_control_id = active_controls[0].id
        if has_expired_verified:
            candidates.append(
                {
                    "recommendation_type": "refresh_evidence",
                    "priority": "high",
                    "status": "open",
                    "title": f"Refresh expired evidence for obligation {obligation.reference_code}",
                    "rationale": "Applicable obligation has expired verified evidence linked to active controls.",
                    "recommended_control_title": None,
                    "recommended_control_description": None,
                    "existing_control_id": existing_control_id,
                    "suggestion_id": None,
                    "confidence_level": "deterministic_exact",
                    "source": "evidence_freshness",
                    "rule_name": "applicable_obligation_expired_verified_evidence",
                }
            )
        elif not has_verified_current:
            candidates.append(
                {
                    "recommendation_type": "add_evidence",
                    "priority": "normal",
                    "status": "open",
                    "title": f"Add current verified evidence for obligation {obligation.reference_code}",
                    "rationale": "Applicable obligation has controls but no verified current evidence.",
                    "recommended_control_title": None,
                    "recommended_control_description": None,
                    "existing_control_id": existing_control_id,
                    "suggestion_id": None,
                    "confidence_level": "deterministic_partial",
                    "source": "evidence_freshness",
                    "rule_name": "applicable_obligation_without_verified_current_evidence",
                }
            )

        return [
            {
                **candidate,
                "provenance_json": self._build_provenance(
                    framework_id=framework_id,
                    obligation_id=obligation.id,
                    obligation_state=state,
                    latest_eval=latest_eval,
                    mapped_control_ids=control_ids,
                    evidence_ids=evidence_ids,
                    suggestion_id=candidate.get("suggestion_id"),
                    rule_name=candidate["rule_name"],
                ),
            }
            for candidate in candidates
        ]

    def generate_for_framework(
        self,
        *,
        organization_id: uuid.UUID,
        framework_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        dry_run: bool,
        include_non_applicable_review: bool,
        limit: int,
    ) -> tuple[RecommendationGenerationRun | None, list[ObligationControlRecommendation | dict[str, Any]], dict[str, Any]]:
        self.require_framework_active_for_org(organization_id=organization_id, framework_id=framework_id)

        obligations = self.db.execute(
            select(Obligation)
            .where(
                Obligation.framework_id == framework_id,
                Obligation.status == "active",
            )
            .order_by(Obligation.reference_code.asc())
            .limit(limit)
        ).scalars().all()

        now = self.now()
        run_row: RecommendationGenerationRun | None = None
        if not dry_run:
            run_row = RecommendationGenerationRun(
                organization_id=organization_id,
                framework_id=framework_id,
                dry_run=False,
                status="running",
                started_at=now,
                created_by_user_id=actor_user_id,
            )
            self.db.add(run_row)
            self.db.flush()

        created_or_preview: list[ObligationControlRecommendation | dict[str, Any]] = []
        created_count = 0
        skipped_dup_count = 0
        would_create_count = 0

        for obligation in obligations:
            candidates = self._candidate_recommendations(
                organization_id=organization_id,
                framework_id=framework_id,
                obligation=obligation,
                include_non_applicable_review=include_non_applicable_review,
            )

            for candidate in candidates:
                duplicate = self.repo.find_open_duplicate(
                    organization_id=organization_id,
                    framework_id=framework_id,
                    obligation_id=obligation.id,
                    recommendation_type=candidate["recommendation_type"],
                    suggestion_id=candidate.get("suggestion_id"),
                    existing_control_id=candidate.get("existing_control_id"),
                )
                if duplicate is not None:
                    skipped_dup_count += 1
                    continue

                if dry_run:
                    would_create_count += 1
                    created_or_preview.append(
                        {
                            "organization_id": organization_id,
                            "framework_id": framework_id,
                            "obligation_id": obligation.id,
                            "suggestion_id": candidate.get("suggestion_id"),
                            "recommendation_type": candidate["recommendation_type"],
                            "priority": candidate["priority"],
                            "status": "open",
                            "title": candidate["title"],
                            "rationale": candidate["rationale"],
                            "recommended_control_title": candidate.get("recommended_control_title"),
                            "recommended_control_description": candidate.get("recommended_control_description"),
                            "existing_control_id": candidate.get("existing_control_id"),
                            "created_control_id": None,
                            "confidence_level": candidate["confidence_level"],
                            "source": candidate["source"],
                            "provenance_json": candidate.get("provenance_json"),
                            "generated_by_user_id": actor_user_id,
                            "generated_at": now,
                            "applied_by_user_id": None,
                            "applied_at": None,
                            "dismissed_by_user_id": None,
                            "dismissed_at": None,
                            "dismissal_reason": None,
                            "metadata_json": None,
                            "created_at": now,
                            "updated_at": now,
                        }
                    )
                    continue

                row = ObligationControlRecommendation(
                    organization_id=organization_id,
                    framework_id=framework_id,
                    obligation_id=obligation.id,
                    suggestion_id=candidate.get("suggestion_id"),
                    recommendation_type=candidate["recommendation_type"],
                    priority=candidate["priority"],
                    status="open",
                    title=candidate["title"],
                    rationale=candidate["rationale"],
                    recommended_control_title=candidate.get("recommended_control_title"),
                    recommended_control_description=candidate.get("recommended_control_description"),
                    existing_control_id=candidate.get("existing_control_id"),
                    confidence_level=candidate["confidence_level"],
                    source=candidate["source"],
                    provenance_json=candidate.get("provenance_json"),
                    generated_by_user_id=actor_user_id,
                    generated_at=now,
                )
                self.db.add(row)
                self.db.flush()
                created_or_preview.append(row)
                created_count += 1

        summary: dict[str, Any] = {
            "organization_id": str(organization_id),
            "framework_id": str(framework_id),
            "dry_run": dry_run,
            "evaluated_obligations_count": len(obligations),
            "recommendations_created_count": created_count,
            "recommendations_skipped_duplicate_count": skipped_dup_count,
            "recommendations_would_create_count": would_create_count,
            "caveat": CONTROL_RECOMMENDATION_CAVEAT,
        }

        if run_row is not None:
            run_row.status = "completed"
            run_row.finished_at = self.now()
            run_row.evaluated_obligations_count = len(obligations)
            run_row.recommendations_created_count = created_count
            run_row.recommendations_skipped_duplicate_count = skipped_dup_count
            run_row.recommendations_would_create_count = 0
            run_row.summary_json = summary
            self.db.flush()

        return run_row, created_or_preview, summary

    def _map_control_to_obligation(
        self,
        *,
        organization_id: uuid.UUID,
        obligation_id: uuid.UUID,
        control_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> None:
        mapping = self.db.execute(
            select(ControlObligationMapping).where(
                ControlObligationMapping.organization_id == organization_id,
                ControlObligationMapping.obligation_id == obligation_id,
                ControlObligationMapping.control_id == control_id,
            )
        ).scalar_one_or_none()
        if mapping is None:
            mapping = ControlObligationMapping(
                organization_id=organization_id,
                obligation_id=obligation_id,
                control_id=control_id,
                mapping_type="supports",
                confidence="manual_confirmed",
                status="active",
                created_by_user_id=actor_user_id,
            )
            self.db.add(mapping)
        elif mapping.status != "active":
            mapping.status = "active"
        self.db.flush()

    def _validate_org_control(self, *, organization_id: uuid.UUID, control_id: uuid.UUID) -> Control:
        control = self.db.execute(
            select(Control).where(
                Control.id == control_id,
                Control.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if control is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control not found")
        if control.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot use archived control")
        return control

    def apply_recommendation(
        self,
        *,
        organization_id: uuid.UUID,
        recommendation_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        existing_control_id: uuid.UUID | None,
        create_control: bool,
        notes: str | None,
    ) -> ObligationControlRecommendation:
        recommendation = self.repo.get_recommendation(recommendation_id)
        if recommendation is None or recommendation.organization_id != organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")
        if recommendation.status != "open":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Recommendation is not open")

        now = self.now()
        created_task_id: uuid.UUID | None = None

        if recommendation.recommendation_type == "create_control":
            if not create_control:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="create_control must be true for create_control recommendations")

            title = recommendation.recommended_control_title or f"Control for obligation {recommendation.obligation_id}"
            control = Control(
                organization_id=organization_id,
                obligation_id=recommendation.obligation_id,
                title=title,
                description=recommendation.recommended_control_description,
                control_type="process",
                status="not_started",
                criticality=self._priority_to_control_criticality(recommendation.priority),
                source="system_suggested",
                created_by_user_id=actor_user_id,
                suggestion_source_id=recommendation.suggestion_id,
                implementation_notes=notes,
            )
            self.db.add(control)
            self.db.flush()
            self._map_control_to_obligation(
                organization_id=organization_id,
                obligation_id=recommendation.obligation_id,
                control_id=control.id,
                actor_user_id=actor_user_id,
            )
            recommendation.created_control_id = control.id
            recommendation.existing_control_id = control.id

        elif recommendation.recommendation_type == "map_existing_control":
            control_id = existing_control_id or recommendation.existing_control_id
            if control_id is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="existing_control_id is required")
            control = self._validate_org_control(organization_id=organization_id, control_id=control_id)
            self._map_control_to_obligation(
                organization_id=organization_id,
                obligation_id=recommendation.obligation_id,
                control_id=control.id,
                actor_user_id=actor_user_id,
            )
            recommendation.existing_control_id = control.id

        elif recommendation.recommendation_type in {"add_evidence", "refresh_evidence"}:
            linked_entity_type = "control" if recommendation.existing_control_id else "obligation"
            linked_entity_id = recommendation.existing_control_id or recommendation.obligation_id
            task = Task(
                organization_id=organization_id,
                title=recommendation.title,
                description=recommendation.rationale,
                status="open",
                priority="high" if recommendation.recommendation_type == "refresh_evidence" else "normal",
                task_type="evidence_request",
                owner_user_id=None,
                created_by_user_id=actor_user_id,
                linked_entity_type=linked_entity_type,
                linked_entity_id=linked_entity_id,
                source="system_generated",
                reminder_status="none",
                metadata_json={
                    "recommendation_id": str(recommendation.id),
                    "notes": notes,
                },
            )
            self.db.add(task)
            self.db.flush()
            created_task_id = task.id

        elif recommendation.recommendation_type == "review_applicability":
            task = Task(
                organization_id=organization_id,
                title=recommendation.title,
                description=recommendation.rationale,
                status="open",
                priority="normal",
                task_type="obligation_review",
                owner_user_id=None,
                created_by_user_id=actor_user_id,
                linked_entity_type="obligation",
                linked_entity_id=recommendation.obligation_id,
                source="system_generated",
                reminder_status="none",
                metadata_json={
                    "recommendation_id": str(recommendation.id),
                    "notes": notes,
                },
            )
            self.db.add(task)
            self.db.flush()
            created_task_id = task.id

        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported recommendation type")

        recommendation.status = "applied"
        recommendation.applied_by_user_id = actor_user_id
        recommendation.applied_at = now
        metadata = recommendation.metadata_json or {}
        if notes:
            metadata["apply_notes"] = notes
        if created_task_id is not None:
            metadata["created_task_id"] = str(created_task_id)
        recommendation.metadata_json = metadata or None
        self.db.flush()
        return recommendation

    def dismiss_recommendation(
        self,
        *,
        organization_id: uuid.UUID,
        recommendation_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        dismissal_reason: str,
    ) -> ObligationControlRecommendation:
        recommendation = self.repo.get_recommendation(recommendation_id)
        if recommendation is None or recommendation.organization_id != organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")
        if recommendation.status != "open":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Recommendation is not open")

        recommendation.status = "dismissed"
        recommendation.dismissed_by_user_id = actor_user_id
        recommendation.dismissed_at = self.now()
        recommendation.dismissal_reason = dismissal_reason
        self.db.flush()
        return recommendation
