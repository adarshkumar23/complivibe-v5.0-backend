from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ai_system_risk_assessment import AISystemRiskAssessment
from app.models.ai_system_risk_classification_record import AISystemRiskClassificationRecord
from app.models.governance_copilot_draft_snapshot import GovernanceCopilotDraftSnapshot
from app.models.governance_recommendation_snapshot import GovernanceRecommendationSnapshot
from app.services.ai_system_risk_assessment_service import AISystemRiskAssessmentService

GOVERNANCE_COPILOT_DRAFT_CAVEAT = (
    "Copilot drafts are deterministic draft previews for human review. "
    "They do not execute actions, create tasks, trigger automation, certify compliance, "
    "or make legal/regulatory determinations."
)
GOVERNANCE_COPILOT_DRAFT_SNAPSHOT_CAVEAT = (
    "Copilot draft snapshots preserve deterministic draft previews at a point in time. "
    "They do not create tasks, trigger automation, approve, certify, or make legal/regulatory determinations."
)

GOVERNANCE_COPILOT_GENERATION_MODE = "deterministic_template"
GOVERNANCE_COPILOT_DRAFT_TYPES: tuple[dict[str, Any], ...] = (
    {
        "draft_type": "ai_system_attention_brief",
        "title": "AI System Attention Brief",
        "description": "Concise AI-system attention draft based on signals and candidate actions.",
        "scope_types": ["ai_system"],
    },
    {
        "draft_type": "risk_assessment_review_brief",
        "title": "Risk Assessment Review Brief",
        "description": "Concise risk-assessment review draft using manual and calculated risk posture fields.",
        "scope_types": ["risk_assessment"],
    },
    {
        "draft_type": "recommendation_snapshot_summary",
        "title": "Recommendation Snapshot Summary",
        "description": "Deterministic summary of candidate actions and disposition overlay for a snapshot.",
        "scope_types": ["recommendation_snapshot"],
    },
    {
        "draft_type": "classification_review_brief",
        "title": "Classification Review Brief",
        "description": "Classification workflow status brief for manual governance review.",
        "scope_types": ["organization", "ai_system", "risk_assessment"],
    },
    {
        "draft_type": "executive_risk_summary",
        "title": "Executive Risk Summary",
        "description": "Leadership-ready deterministic risk posture summary at organization scope.",
        "scope_types": ["organization"],
    },
    {
        "draft_type": "action_plan_brief",
        "title": "Action Plan Brief",
        "description": "Deterministic next-best-attention action plan from candidate actions.",
        "scope_types": ["organization", "ai_system", "risk_assessment"],
    },
)


class GovernanceCopilotDraftService:
    def __init__(self, db: Session):
        self.db = db
        self.risk_service = AISystemRiskAssessmentService(db)

    @staticmethod
    def _priority_rank(priority_band: str) -> int:
        return {"low": 1, "medium": 2, "high": 3, "urgent": 4}.get(priority_band, 0)

    @staticmethod
    def _dedupe_lines(lines: list[str], *, max_items: int = 5) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for line in lines:
            value = str(line).strip()
            if not value:
                continue
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(value)
            if len(out) >= max_items:
                break
        return out

    @staticmethod
    def _draft_type_config(draft_type: str) -> dict[str, Any] | None:
        for item in GOVERNANCE_COPILOT_DRAFT_TYPES:
            if item["draft_type"] == draft_type:
                return dict(item)
        return None

    @classmethod
    def draft_type_catalog(cls) -> list[dict[str, Any]]:
        rows = [dict(item) for item in GOVERNANCE_COPILOT_DRAFT_TYPES]
        rows.sort(key=lambda row: str(row["draft_type"]))
        return rows

    def _validate_scope(
        self,
        *,
        organization_id: uuid.UUID,
        scope_type: str,
        scope_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        if scope_type == "organization":
            if scope_id is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="scope_id must be null for organization scope",
                )
            return {"scope_type": scope_type, "scope_id": None}

        if scope_type == "ai_system":
            if scope_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="scope_id is required for ai_system scope",
                )
            self.risk_service.ai_system_service.require_ai_system_in_org(
                organization_id=organization_id,
                ai_system_id=scope_id,
            )
            return {"scope_type": scope_type, "scope_id": scope_id, "ai_system_id": scope_id}

        if scope_type == "risk_assessment":
            if scope_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="scope_id is required for risk_assessment scope",
                )
            assessment = self.risk_service.require_assessment(
                organization_id=organization_id,
                assessment_id=scope_id,
            )
            return {
                "scope_type": scope_type,
                "scope_id": scope_id,
                "risk_assessment_id": assessment.id,
                "ai_system_id": assessment.ai_system_id,
                "assessment": assessment,
            }

        if scope_type == "recommendation_snapshot":
            if scope_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="scope_id is required for recommendation_snapshot scope",
                )
            snapshot = self.risk_service.require_recommendation_snapshot(
                organization_id=organization_id,
                snapshot_id=scope_id,
            )
            return {
                "scope_type": scope_type,
                "scope_id": scope_id,
                "recommendation_snapshot_id": snapshot.id,
                "snapshot": snapshot,
            }

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid scope_type")

    def _signals_for_context(
        self,
        *,
        organization_id: uuid.UUID,
        related_ai_system_id: uuid.UUID | None,
        related_risk_assessment_id: uuid.UUID | None,
        include_resolved_signals: bool,
    ) -> list[dict[str, Any]]:
        rows = self.risk_service.list_prioritized_governance_signals(
            organization_id=organization_id,
            domain="ai_risk",
            entity_type=None,
            related_ai_system_id=related_ai_system_id,
            related_risk_assessment_id=related_risk_assessment_id,
            signal_type=None,
            reason_code=None,
            severity=None,
            status_filter="open",
            priority_band=None,
            limit=500,
            offset=0,
        )
        if include_resolved_signals:
            rows.extend(
                self.risk_service.list_prioritized_governance_signals(
                    organization_id=organization_id,
                    domain="ai_risk",
                    entity_type=None,
                    related_ai_system_id=related_ai_system_id,
                    related_risk_assessment_id=related_risk_assessment_id,
                    signal_type=None,
                    reason_code=None,
                    severity=None,
                    status_filter="resolved",
                    priority_band=None,
                    limit=500,
                    offset=0,
                )
            )
            rows.sort(
                key=lambda item: (
                    -float(item["priority_score"]),
                    item["created_at"],
                    str(item["signal_id"]),
                )
            )
        return rows

    def _candidate_actions_for_context(
        self,
        *,
        organization_id: uuid.UUID,
        related_ai_system_id: uuid.UUID | None,
        related_risk_assessment_id: uuid.UUID | None,
    ) -> list[dict[str, Any]]:
        return self.risk_service.list_candidate_actions(
            organization_id=organization_id,
            related_ai_system_id=related_ai_system_id,
            related_risk_assessment_id=related_risk_assessment_id,
            entity_type=None,
            entity_id=None,
            priority_band=None,
            action_type=None,
            reason_code=None,
            limit=500,
            offset=0,
        )

    def _base_draft_payload(
        self,
        *,
        draft_type: str,
        title: str,
        executive_summary: str,
        key_findings: list[str],
        recommended_next_steps: list[str],
        open_questions: list[str],
        source_signal_ids: list[uuid.UUID],
        source_recommendation_snapshot_id: uuid.UUID | None,
        source_action_identity_hashes: list[str],
        source_entities_json: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "draft_type": draft_type,
            "title": title,
            "executive_summary": executive_summary,
            "key_findings": self._dedupe_lines(key_findings, max_items=5),
            "recommended_next_steps": self._dedupe_lines(recommended_next_steps, max_items=5),
            "open_questions": self._dedupe_lines(open_questions, max_items=5),
            "source_signal_ids": sorted(set(source_signal_ids), key=lambda value: str(value)),
            "source_recommendation_snapshot_id": source_recommendation_snapshot_id,
            "source_action_identity_hashes": sorted(set(source_action_identity_hashes)),
            "source_entities_json": source_entities_json,
            "generated_at": self.risk_service.now(),
            "generation_mode": GOVERNANCE_COPILOT_GENERATION_MODE,
            "caveat": GOVERNANCE_COPILOT_DRAFT_CAVEAT,
        }

    def _ai_system_attention_brief(
        self,
        *,
        organization_id: uuid.UUID,
        ai_system_id: uuid.UUID,
        include_resolved_signals: bool,
    ) -> dict[str, Any]:
        attention = self.risk_service.ai_system_attention_view(
            organization_id=organization_id,
            ai_system_id=ai_system_id,
        )
        actions_payload = self.risk_service.ai_system_candidate_actions(
            organization_id=organization_id,
            ai_system_id=ai_system_id,
        )
        actions = list(actions_payload["actions"])
        signals = self._signals_for_context(
            organization_id=organization_id,
            related_ai_system_id=ai_system_id,
            related_risk_assessment_id=None,
            include_resolved_signals=include_resolved_signals,
        )

        top_band = str(attention["highest_priority_band"])
        open_count = int(attention["open_signal_count"])
        executive_summary = (
            f"AI system {ai_system_id} currently has {open_count} open governance signals with highest priority band "
            f"{top_band}. Deterministic candidate-action analysis identifies {len(actions)} next-best-attention items."
        )

        key_findings = [
            f"Open governance signals: {open_count}.",
            f"Highest signal priority band: {top_band}.",
            f"Latest manual risk level: {attention.get('latest_manual_risk_level') or 'unknown'}.",
            (
                "Latest calculated residual risk level: "
                f"{attention.get('latest_calculated_residual_risk_level') or 'unknown'}."
            ),
            f"Candidate actions currently available: {len(actions)}.",
        ]
        recommended_next_steps = [
            f"{item['title']} ({item['action_key']})."
            for item in actions[:5]
        ]
        open_questions = []
        if not actions:
            open_questions.append("No candidate actions are currently mapped from open signals; should signal refresh be run?")
        if not attention.get("latest_risk_assessment_id"):
            open_questions.append("No risk assessment is linked yet; should a manual risk assessment be created?")

        source_signal_ids = [item["signal_id"] for item in signals]
        source_action_hashes = [
            self.risk_service.recommendation_action_identity_hash(action)
            for action in actions
        ]
        return self._base_draft_payload(
            draft_type="ai_system_attention_brief",
            title=f"AI System Attention Brief: {ai_system_id}",
            executive_summary=executive_summary,
            key_findings=key_findings,
            recommended_next_steps=recommended_next_steps,
            open_questions=open_questions,
            source_signal_ids=source_signal_ids,
            source_recommendation_snapshot_id=None,
            source_action_identity_hashes=source_action_hashes,
            source_entities_json={
                "scope_type": "ai_system",
                "ai_system_id": str(ai_system_id),
                "latest_risk_assessment_id": (
                    str(attention["latest_risk_assessment_id"])
                    if attention.get("latest_risk_assessment_id")
                    else None
                ),
                "latest_manual_risk_level": attention.get("latest_manual_risk_level"),
                "latest_calculated_residual_risk_level": attention.get("latest_calculated_residual_risk_level"),
            },
        )

    def _risk_assessment_review_brief(
        self,
        *,
        organization_id: uuid.UUID,
        assessment: AISystemRiskAssessment,
        include_resolved_signals: bool,
    ) -> dict[str, Any]:
        actions_payload = self.risk_service.risk_assessment_candidate_actions(
            organization_id=organization_id,
            assessment_id=assessment.id,
        )
        actions = list(actions_payload["actions"])
        signals = self._signals_for_context(
            organization_id=organization_id,
            related_ai_system_id=assessment.ai_system_id,
            related_risk_assessment_id=assessment.id,
            include_resolved_signals=include_resolved_signals,
        )
        has_evidence_gap_signal = any(
            str(item.get("reason_code")) == "classification_has_unlinked_evidence"
            for item in signals
        )

        executive_summary = (
            f"Risk assessment {assessment.id} is in status {assessment.status} with manual risk level "
            f"{assessment.risk_level}. Deterministic signal and candidate-action context indicates "
            f"{len(signals)} relevant governance signals and {len(actions)} candidate actions."
        )
        key_findings = [
            f"Manual risk posture: risk_level={assessment.risk_level}, likelihood={assessment.likelihood}, impact={assessment.impact}.",
            (
                "Calculated posture: calculated_risk_level="
                f"{assessment.calculated_risk_level or 'unknown'}, residual={assessment.calculated_residual_risk_level or 'unknown'}."
            ),
            (
                "Classification status: "
                f"{assessment.classification_status or 'none'} / review={assessment.latest_classification_review_status or 'none'}."
            ),
            f"Open/selected governance signals considered: {len(signals)}.",
            f"Candidate actions available: {len(actions)}.",
        ]
        if has_evidence_gap_signal:
            key_findings.append("Evidence-linkage gap signal is present and should be addressed before review closure.")

        recommended_next_steps = [
            f"{item['title']} ({item['action_key']})."
            for item in actions[:5]
        ]
        open_questions = []
        if assessment.latest_classification_id is None:
            open_questions.append("No classification record is linked; should one be created before completion?")
        if has_evidence_gap_signal:
            open_questions.append("Which evidence references should be linked to support current classification labels?")

        source_signal_ids = [item["signal_id"] for item in signals]
        source_action_hashes = [
            self.risk_service.recommendation_action_identity_hash(action)
            for action in actions
        ]
        return self._base_draft_payload(
            draft_type="risk_assessment_review_brief",
            title=f"Risk Assessment Review Brief: {assessment.id}",
            executive_summary=executive_summary,
            key_findings=key_findings,
            recommended_next_steps=recommended_next_steps,
            open_questions=open_questions,
            source_signal_ids=source_signal_ids,
            source_recommendation_snapshot_id=None,
            source_action_identity_hashes=source_action_hashes,
            source_entities_json={
                "scope_type": "risk_assessment",
                "risk_assessment_id": str(assessment.id),
                "ai_system_id": str(assessment.ai_system_id),
                "assessment_status": assessment.status,
                "classification_status": assessment.classification_status,
                "latest_classification_review_status": assessment.latest_classification_review_status,
            },
        )

    def _recommendation_snapshot_summary(
        self,
        *,
        organization_id: uuid.UUID,
        snapshot: GovernanceRecommendationSnapshot,
        include_dispositions: bool,
        include_dismissed_recommendations: bool,
    ) -> dict[str, Any]:
        actions_payload = self.risk_service.list_snapshot_actions(
            organization_id=organization_id,
            snapshot_id=snapshot.id,
            include_dispositions=include_dispositions,
        )
        actions = list(actions_payload["actions"])
        disposition_counts: dict[str, int] = {}
        for action in actions:
            disposition = action.get("disposition") if include_dispositions else None
            if not isinstance(disposition, dict):
                continue
            status_value = str(disposition.get("disposition_status") or "")
            if not status_value:
                continue
            if status_value == "dismissed" and not include_dismissed_recommendations:
                continue
            disposition_counts[status_value] = int(disposition_counts.get(status_value, 0) + 1)

        urgent_or_high = [
            item for item in actions if str(item.get("priority_band")) in {"urgent", "high"}
        ]
        diff_payload = snapshot.diff_from_previous_json if isinstance(snapshot.diff_from_previous_json, dict) else {}
        executive_summary = (
            f"Recommendation snapshot {snapshot.id} contains {len(actions)} deterministic candidate actions for "
            f"scope {snapshot.scope_type}. {len(urgent_or_high)} actions are currently urgent/high priority."
        )

        key_findings = [
            f"Candidate action count: {len(actions)}.",
            f"Urgent/high actions: {len(urgent_or_high)}.",
            f"Disposition counts: {disposition_counts or {}}.",
            (
                "Changes from previous snapshot: "
                f"added={len(diff_payload.get('added_actions', []))}, removed={len(diff_payload.get('removed_actions', []))}, "
                f"changed={len(diff_payload.get('changed_actions', []))}."
            ),
            f"Snapshot version: {snapshot.snapshot_version}.",
        ]

        recommended_next_steps = [
            f"{item['title']} ({item['action_key']})."
            for item in urgent_or_high[:5]
        ]
        if not recommended_next_steps:
            recommended_next_steps = [
                f"{item['title']} ({item['action_key']})."
                for item in actions[:5]
            ]

        open_questions = []
        if include_dispositions and not disposition_counts:
            open_questions.append("No disposition metadata is recorded yet; should operators acknowledge or defer key actions?")

        source_signal_ids = [uuid.UUID(str(value)) for value in (snapshot.source_signal_ids_json or [])]
        source_action_hashes = [str(item.get("action_identity_hash")) for item in actions if item.get("action_identity_hash")]
        return self._base_draft_payload(
            draft_type="recommendation_snapshot_summary",
            title=f"Recommendation Snapshot Summary: {snapshot.id}",
            executive_summary=executive_summary,
            key_findings=key_findings,
            recommended_next_steps=recommended_next_steps,
            open_questions=open_questions,
            source_signal_ids=source_signal_ids,
            source_recommendation_snapshot_id=snapshot.id,
            source_action_identity_hashes=source_action_hashes,
            source_entities_json={
                "scope_type": snapshot.scope_type,
                "scope_id": str(snapshot.scope_id) if snapshot.scope_id else None,
                "snapshot_version": int(snapshot.snapshot_version),
                "previous_snapshot_id": str(snapshot.previous_snapshot_id) if snapshot.previous_snapshot_id else None,
                "include_dispositions": include_dispositions,
            },
        )

    def _classification_review_brief(
        self,
        *,
        organization_id: uuid.UUID,
        scope_type: str,
        scope_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        query = select(AISystemRiskClassificationRecord).where(
            AISystemRiskClassificationRecord.organization_id == organization_id,
            AISystemRiskClassificationRecord.archived_at.is_(None),
        )
        if scope_type == "risk_assessment" and scope_id is not None:
            query = query.where(AISystemRiskClassificationRecord.risk_assessment_id == scope_id)
        elif scope_type == "ai_system" and scope_id is not None:
            query = query.where(AISystemRiskClassificationRecord.ai_system_id == scope_id)
        query = query.order_by(AISystemRiskClassificationRecord.created_at.desc(), AISystemRiskClassificationRecord.id.desc()).limit(50)
        rows = list(self.db.execute(query).scalars().all())

        by_review_status: dict[str, int] = {}
        by_confidence: dict[str, int] = {}
        for row in rows:
            by_review_status[row.review_status] = int(by_review_status.get(row.review_status, 0) + 1)
            by_confidence[row.confidence_level] = int(by_confidence.get(row.confidence_level, 0) + 1)

        executive_summary = (
            f"Classification review brief for {scope_type} scope identifies {len(rows)} non-archived classification records. "
            f"Top review-state distribution: {by_review_status or {'none': 0}}."
        )
        key_findings = [
            f"Classification records considered: {len(rows)}.",
            f"By review status: {by_review_status or {}}.",
            f"By confidence level: {by_confidence or {}}.",
            f"Changes requested count: {int(by_review_status.get('changes_requested', 0))}.",
            f"Rejected count: {int(by_review_status.get('rejected', 0))}.",
        ]
        recommended_next_steps = []
        if by_review_status.get("changes_requested"):
            recommended_next_steps.append("Address pending classification change requests and resubmit for review.")
        if by_review_status.get("in_review"):
            recommended_next_steps.append("Complete manual review decisions for records currently in review.")
        if by_confidence.get("low"):
            recommended_next_steps.append("Strengthen justification for low-confidence classifications with explicit supporting evidence.")
        open_questions = []
        if not rows:
            open_questions.append("No active classification records found for scope; should a classification be created?")

        source_entities = {
            "scope_type": scope_type,
            "scope_id": str(scope_id) if scope_id else None,
            "classification_ids": [str(row.id) for row in rows[:20]],
        }
        return self._base_draft_payload(
            draft_type="classification_review_brief",
            title=f"Classification Review Brief: {scope_type}",
            executive_summary=executive_summary,
            key_findings=key_findings,
            recommended_next_steps=recommended_next_steps,
            open_questions=open_questions,
            source_signal_ids=[],
            source_recommendation_snapshot_id=None,
            source_action_identity_hashes=[],
            source_entities_json=source_entities,
        )

    def _action_plan_brief(
        self,
        *,
        organization_id: uuid.UUID,
        related_ai_system_id: uuid.UUID | None,
        related_risk_assessment_id: uuid.UUID | None,
        scope_type: str,
        scope_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        actions = self._candidate_actions_for_context(
            organization_id=organization_id,
            related_ai_system_id=related_ai_system_id,
            related_risk_assessment_id=related_risk_assessment_id,
        )
        by_type: dict[str, int] = {}
        by_band: dict[str, int] = {}
        for row in actions:
            by_type[str(row["action_type"])] = int(by_type.get(str(row["action_type"]), 0) + 1)
            by_band[str(row["priority_band"])] = int(by_band.get(str(row["priority_band"]), 0) + 1)

        executive_summary = (
            f"Action-plan brief for {scope_type} scope identifies {len(actions)} deterministic candidate actions "
            "for manual follow-up sequencing."
        )
        key_findings = [
            f"Candidate actions: {len(actions)}.",
            f"By action type: {by_type or {}}.",
            f"By priority band: {by_band or {}}.",
            f"Urgent actions: {int(by_band.get('urgent', 0))}.",
            f"High actions: {int(by_band.get('high', 0))}.",
        ]
        recommended_next_steps = [f"{item['title']} ({item['action_key']})." for item in actions[:5]]
        open_questions = []
        if not actions:
            open_questions.append("No mapped candidate actions found; should signal refresh be run to update attention inputs?")

        source_signal_ids: list[uuid.UUID] = []
        source_action_hashes: list[str] = []
        for action in actions:
            source_signal_ids.extend(action.get("source_signal_ids", []))
            source_action_hashes.append(self.risk_service.recommendation_action_identity_hash(action))

        return self._base_draft_payload(
            draft_type="action_plan_brief",
            title=f"Action Plan Brief: {scope_type}",
            executive_summary=executive_summary,
            key_findings=key_findings,
            recommended_next_steps=recommended_next_steps,
            open_questions=open_questions,
            source_signal_ids=source_signal_ids,
            source_recommendation_snapshot_id=None,
            source_action_identity_hashes=source_action_hashes,
            source_entities_json={
                "scope_type": scope_type,
                "scope_id": str(scope_id) if scope_id else None,
                "related_ai_system_id": str(related_ai_system_id) if related_ai_system_id else None,
                "related_risk_assessment_id": (
                    str(related_risk_assessment_id) if related_risk_assessment_id else None
                ),
            },
        )

    def _executive_risk_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        priority_summary = self.risk_service.governance_signal_priority_summary(organization_id=organization_id)
        action_summary = self.risk_service.candidate_action_summary(organization_id=organization_id)
        disposition_summary = self.risk_service.recommendation_action_disposition_summary(organization_id=organization_id)
        prioritized = self.risk_service.list_prioritized_governance_signals(
            organization_id=organization_id,
            domain="ai_risk",
            entity_type=None,
            related_ai_system_id=None,
            related_risk_assessment_id=None,
            signal_type=None,
            reason_code=None,
            severity=None,
            status_filter="open",
            priority_band=None,
            limit=100,
            offset=0,
        )

        latest_snapshot_id = None
        try:
            latest_snapshot = self.risk_service.latest_recommendation_snapshot(
                organization_id=organization_id,
                scope_type="organization",
                scope_id=None,
            )
            latest_snapshot_id = latest_snapshot.id
        except HTTPException:
            latest_snapshot_id = None

        executive_summary = (
            "Executive risk summary highlights deterministic governance attention load across AI risk surfaces. "
            f"Current open signal volume is {priority_summary['total_open_signals']} with "
            f"{priority_summary['urgent_signal_count']} urgent and {priority_summary['high_signal_count']} high signals."
        )
        key_findings = [
            f"Open governance signals: {priority_summary['total_open_signals']}.",
            f"Urgent/high signals: {priority_summary['urgent_signal_count']}/{priority_summary['high_signal_count']}.",
            f"Candidate actions: {action_summary['total_candidate_actions']}.",
            f"Disposition records: {disposition_summary['total_dispositions']}.",
            f"Top AI systems by attention: {len(priority_summary.get('top_ai_systems_by_attention', []))} tracked entries.",
        ]
        recommended_next_steps = [
            f"Prioritize operator review for top action key {item['action_key']} (count={item['count']})."
            for item in action_summary.get("top_action_keys", [])[:5]
        ]
        open_questions = []
        if latest_snapshot_id is None:
            open_questions.append("No organization-scope recommendation snapshot is available yet; should one be captured now?")

        source_signal_ids = [item["signal_id"] for item in prioritized]
        return self._base_draft_payload(
            draft_type="executive_risk_summary",
            title="Executive AI Risk Summary",
            executive_summary=executive_summary,
            key_findings=key_findings,
            recommended_next_steps=recommended_next_steps,
            open_questions=open_questions,
            source_signal_ids=source_signal_ids,
            source_recommendation_snapshot_id=latest_snapshot_id,
            source_action_identity_hashes=[],
            source_entities_json={
                "scope_type": "organization",
                "top_ai_systems_by_attention": priority_summary.get("top_ai_systems_by_attention", []),
                "top_action_keys": action_summary.get("top_action_keys", []),
                "disposition_by_status": disposition_summary.get("by_status", {}),
            },
        )

    def preview_draft(
        self,
        *,
        organization_id: uuid.UUID,
        draft_type: str,
        scope_type: str,
        scope_id: uuid.UUID | None,
        include_resolved_signals: bool,
        include_dismissed_recommendations: bool,
    ) -> dict[str, Any]:
        draft_cfg = self._draft_type_config(draft_type)
        if draft_cfg is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid draft_type")

        context = self._validate_scope(
            organization_id=organization_id,
            scope_type=scope_type,
            scope_id=scope_id,
        )

        allowed_scope_types = set(str(item) for item in draft_cfg.get("scope_types", []))
        if scope_type not in allowed_scope_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"draft_type '{draft_type}' does not support scope_type '{scope_type}'",
            )

        if draft_type == "ai_system_attention_brief":
            return self._ai_system_attention_brief(
                organization_id=organization_id,
                ai_system_id=context["ai_system_id"],
                include_resolved_signals=include_resolved_signals,
            )

        if draft_type == "risk_assessment_review_brief":
            assessment = context.get("assessment")
            if not isinstance(assessment, AISystemRiskAssessment):
                assessment = self.risk_service.require_assessment(
                    organization_id=organization_id,
                    assessment_id=context["risk_assessment_id"],
                )
            return self._risk_assessment_review_brief(
                organization_id=organization_id,
                assessment=assessment,
                include_resolved_signals=include_resolved_signals,
            )

        if draft_type == "recommendation_snapshot_summary":
            snapshot = context.get("snapshot")
            if not isinstance(snapshot, GovernanceRecommendationSnapshot):
                snapshot = self.risk_service.require_recommendation_snapshot(
                    organization_id=organization_id,
                    snapshot_id=context["recommendation_snapshot_id"],
                )
            return self._recommendation_snapshot_summary(
                organization_id=organization_id,
                snapshot=snapshot,
                include_dispositions=True,
                include_dismissed_recommendations=include_dismissed_recommendations,
            )

        if draft_type == "classification_review_brief":
            return self._classification_review_brief(
                organization_id=organization_id,
                scope_type=scope_type,
                scope_id=scope_id,
            )

        if draft_type == "executive_risk_summary":
            return self._executive_risk_summary(organization_id=organization_id)

        if draft_type == "action_plan_brief":
            return self._action_plan_brief(
                organization_id=organization_id,
                related_ai_system_id=context.get("ai_system_id"),
                related_risk_assessment_id=context.get("risk_assessment_id"),
                scope_type=scope_type,
                scope_id=scope_id,
            )

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported draft_type")

    def _draft_snapshot_source_context_hash(self, *, draft_payload: dict[str, Any]) -> str:
        return self.risk_service.sha256_hexdigest(
            {
                "draft_type": draft_payload["draft_type"],
                "scope_type": str(draft_payload["source_entities_json"].get("scope_type") or ""),
                "scope_id": str(draft_payload["source_entities_json"].get("scope_id") or ""),
                "source_entities_json": self.risk_service._serialize_json_value(
                    draft_payload.get("source_entities_json", {})
                ),
                "source_signal_ids": sorted(str(value) for value in draft_payload.get("source_signal_ids", [])),
                "source_recommendation_snapshot_id": (
                    str(draft_payload.get("source_recommendation_snapshot_id"))
                    if draft_payload.get("source_recommendation_snapshot_id")
                    else None
                ),
                "source_action_identity_hashes": sorted(
                    str(value) for value in draft_payload.get("source_action_identity_hashes", [])
                ),
            }
        )

    def _draft_snapshot_hash(
        self,
        *,
        draft_type: str,
        scope_type: str,
        scope_id: uuid.UUID | None,
        draft_payload: dict[str, Any],
        source_context_hash: str,
    ) -> str:
        return self.risk_service.sha256_hexdigest(
            {
                "draft_type": draft_type,
                "scope_type": scope_type,
                "scope_id": str(scope_id) if scope_id else None,
                "draft_payload_json": self.risk_service._serialize_json_value(draft_payload),
                "source_context_hash": source_context_hash,
            }
        )

    @staticmethod
    def _string_list_diff(*, before: list[str], after: list[str]) -> tuple[list[str], list[str]]:
        before_set = {str(item) for item in before if str(item).strip()}
        after_set = {str(item) for item in after if str(item).strip()}
        return sorted(after_set - before_set), sorted(before_set - after_set)

    def _draft_diff_from_payloads(
        self,
        *,
        base_payload: dict[str, Any],
        compare_payload: dict[str, Any],
    ) -> dict[str, Any]:
        added_findings, removed_findings = self._string_list_diff(
            before=[str(item) for item in base_payload.get("key_findings", [])],
            after=[str(item) for item in compare_payload.get("key_findings", [])],
        )
        added_steps, removed_steps = self._string_list_diff(
            before=[str(item) for item in base_payload.get("recommended_next_steps", [])],
            after=[str(item) for item in compare_payload.get("recommended_next_steps", [])],
        )
        added_questions, removed_questions = self._string_list_diff(
            before=[str(item) for item in base_payload.get("open_questions", [])],
            after=[str(item) for item in compare_payload.get("open_questions", [])],
        )
        added_signals, removed_signals = self._string_list_diff(
            before=[str(item) for item in base_payload.get("source_signal_ids", [])],
            after=[str(item) for item in compare_payload.get("source_signal_ids", [])],
        )
        added_hashes, removed_hashes = self._string_list_diff(
            before=[str(item) for item in base_payload.get("source_action_identity_hashes", [])],
            after=[str(item) for item in compare_payload.get("source_action_identity_hashes", [])],
        )
        return {
            "executive_summary_changed": str(base_payload.get("executive_summary", "")) != str(
                compare_payload.get("executive_summary", "")
            ),
            "added_key_findings": added_findings,
            "removed_key_findings": removed_findings,
            "added_next_steps": added_steps,
            "removed_next_steps": removed_steps,
            "added_open_questions": added_questions,
            "removed_open_questions": removed_questions,
            "source_reference_changes": {
                "source_signals_added": added_signals,
                "source_signals_removed": removed_signals,
                "source_action_hashes_added": added_hashes,
                "source_action_hashes_removed": removed_hashes,
                "source_recommendation_snapshot_changed": str(
                    base_payload.get("source_recommendation_snapshot_id") or ""
                )
                != str(compare_payload.get("source_recommendation_snapshot_id") or ""),
                "source_entities_changed": self.risk_service._serialize_json_value(
                    base_payload.get("source_entities_json", {})
                )
                != self.risk_service._serialize_json_value(compare_payload.get("source_entities_json", {})),
            },
            "algorithm": "governance_copilot_draft_snapshot_diff_v1",
        }

    def preview_draft_snapshot(
        self,
        *,
        organization_id: uuid.UUID,
        draft_type: str,
        scope_type: str,
        scope_id: uuid.UUID | None,
        include_resolved_signals: bool,
        include_dismissed_recommendations: bool,
    ) -> dict[str, Any]:
        payload = self.preview_draft(
            organization_id=organization_id,
            draft_type=draft_type,
            scope_type=scope_type,
            scope_id=scope_id,
            include_resolved_signals=include_resolved_signals,
            include_dismissed_recommendations=include_dismissed_recommendations,
        )
        source_context_hash = self._draft_snapshot_source_context_hash(draft_payload=payload)
        return {
            "draft_type": draft_type,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "draft_payload_json": self.risk_service._serialize_json_value(payload),
            "source_entities_json": self.risk_service._serialize_json_value(payload.get("source_entities_json", {})),
            "source_signal_ids": list(payload.get("source_signal_ids", [])),
            "source_recommendation_snapshot_id": payload.get("source_recommendation_snapshot_id"),
            "source_action_identity_hashes": list(payload.get("source_action_identity_hashes", [])),
            "source_context_hash": source_context_hash,
            "caveat": GOVERNANCE_COPILOT_DRAFT_SNAPSHOT_CAVEAT,
        }

    def create_draft_snapshot(
        self,
        *,
        organization_id: uuid.UUID,
        draft_type: str,
        scope_type: str,
        scope_id: uuid.UUID | None,
        include_resolved_signals: bool,
        include_dismissed_recommendations: bool,
        actor_user_id: uuid.UUID | None,
    ) -> GovernanceCopilotDraftSnapshot:
        preview = self.preview_draft_snapshot(
            organization_id=organization_id,
            draft_type=draft_type,
            scope_type=scope_type,
            scope_id=scope_id,
            include_resolved_signals=include_resolved_signals,
            include_dismissed_recommendations=include_dismissed_recommendations,
        )
        draft_payload_json = dict(preview["draft_payload_json"])
        source_context_hash = str(preview["source_context_hash"])
        snapshot_sha256 = self._draft_snapshot_hash(
            draft_type=draft_type,
            scope_type=scope_type,
            scope_id=scope_id,
            draft_payload=draft_payload_json,
            source_context_hash=source_context_hash,
        )
        previous = self.db.execute(
            select(GovernanceCopilotDraftSnapshot)
            .where(
                GovernanceCopilotDraftSnapshot.organization_id == organization_id,
                GovernanceCopilotDraftSnapshot.draft_type == draft_type,
                GovernanceCopilotDraftSnapshot.scope_type == scope_type,
                GovernanceCopilotDraftSnapshot.scope_id == scope_id,
            )
            .order_by(
                GovernanceCopilotDraftSnapshot.snapshot_version.desc(),
                GovernanceCopilotDraftSnapshot.created_at.desc(),
                GovernanceCopilotDraftSnapshot.id.desc(),
            )
            .limit(1)
        ).scalar_one_or_none()
        snapshot_version = 1 if previous is None else int(previous.snapshot_version + 1)
        diff_from_previous_json = None
        if previous is not None:
            diff_from_previous_json = self._draft_diff_from_payloads(
                base_payload=(
                    previous.draft_payload_json if isinstance(previous.draft_payload_json, dict) else {}
                ),
                compare_payload=draft_payload_json,
            )
        row = GovernanceCopilotDraftSnapshot(
            organization_id=organization_id,
            draft_type=draft_type,
            scope_type=scope_type,
            scope_id=scope_id,
            draft_payload_json=draft_payload_json,
            source_entities_json=self.risk_service._serialize_json_value(preview["source_entities_json"]),
            source_signal_ids_json=[str(item) for item in preview["source_signal_ids"]],
            source_recommendation_snapshot_id=preview["source_recommendation_snapshot_id"],
            source_action_identity_hashes_json=[
                str(item) for item in preview["source_action_identity_hashes"]
            ],
            source_context_hash=source_context_hash,
            snapshot_sha256=snapshot_sha256,
            snapshot_version=snapshot_version,
            previous_snapshot_id=previous.id if previous else None,
            diff_from_previous_json=diff_from_previous_json,
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_draft_snapshots(
        self,
        *,
        organization_id: uuid.UUID,
        draft_type: str | None,
        scope_type: str | None,
        scope_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> list[GovernanceCopilotDraftSnapshot]:
        query = select(GovernanceCopilotDraftSnapshot).where(
            GovernanceCopilotDraftSnapshot.organization_id == organization_id
        )
        if draft_type is not None:
            if self._draft_type_config(draft_type) is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid draft_type")
            query = query.where(GovernanceCopilotDraftSnapshot.draft_type == draft_type)
        if scope_type is not None:
            if scope_type not in {"organization", "ai_system", "risk_assessment", "recommendation_snapshot"}:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid scope_type")
            query = query.where(GovernanceCopilotDraftSnapshot.scope_type == scope_type)
        if scope_id is not None:
            query = query.where(GovernanceCopilotDraftSnapshot.scope_id == scope_id)
        query = query.order_by(
            GovernanceCopilotDraftSnapshot.created_at.desc(),
            GovernanceCopilotDraftSnapshot.id.desc(),
        ).offset(offset).limit(limit)
        return list(self.db.execute(query).scalars().all())

    def require_draft_snapshot(
        self,
        *,
        organization_id: uuid.UUID,
        snapshot_id: uuid.UUID,
    ) -> GovernanceCopilotDraftSnapshot:
        row = self.db.execute(
            select(GovernanceCopilotDraftSnapshot).where(
                GovernanceCopilotDraftSnapshot.organization_id == organization_id,
                GovernanceCopilotDraftSnapshot.id == snapshot_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Copilot draft snapshot not found")
        return row

    def diff_draft_snapshots(
        self,
        *,
        organization_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        compare_to_snapshot_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        base = self.require_draft_snapshot(organization_id=organization_id, snapshot_id=snapshot_id)
        if compare_to_snapshot_id is None:
            if base.previous_snapshot_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No previous snapshot available for this draft scope",
                )
            compare = self.require_draft_snapshot(
                organization_id=organization_id,
                snapshot_id=base.previous_snapshot_id,
            )
        else:
            compare = self.require_draft_snapshot(
                organization_id=organization_id,
                snapshot_id=compare_to_snapshot_id,
            )
        diff = self._draft_diff_from_payloads(
            base_payload=(compare.draft_payload_json if isinstance(compare.draft_payload_json, dict) else {}),
            compare_payload=(base.draft_payload_json if isinstance(base.draft_payload_json, dict) else {}),
        )
        return {
            "base_snapshot_id": base.id,
            "compare_snapshot_id": compare.id,
            "executive_summary_changed": bool(diff["executive_summary_changed"]),
            "added_key_findings": list(diff["added_key_findings"]),
            "removed_key_findings": list(diff["removed_key_findings"]),
            "added_next_steps": list(diff["added_next_steps"]),
            "removed_next_steps": list(diff["removed_next_steps"]),
            "added_open_questions": list(diff["added_open_questions"]),
            "removed_open_questions": list(diff["removed_open_questions"]),
            "source_reference_changes": dict(diff["source_reference_changes"]),
            "caveat": GOVERNANCE_COPILOT_DRAFT_SNAPSHOT_CAVEAT,
        }

    def latest_draft_snapshot(
        self,
        *,
        organization_id: uuid.UUID,
        draft_type: str,
        scope_type: str,
        scope_id: uuid.UUID | None,
    ) -> GovernanceCopilotDraftSnapshot:
        if self._draft_type_config(draft_type) is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid draft_type")
        self._validate_scope(
            organization_id=organization_id,
            scope_type=scope_type,
            scope_id=scope_id,
        )
        row = self.db.execute(
            select(GovernanceCopilotDraftSnapshot)
            .where(
                GovernanceCopilotDraftSnapshot.organization_id == organization_id,
                GovernanceCopilotDraftSnapshot.draft_type == draft_type,
                GovernanceCopilotDraftSnapshot.scope_type == scope_type,
                GovernanceCopilotDraftSnapshot.scope_id == scope_id,
            )
            .order_by(
                GovernanceCopilotDraftSnapshot.snapshot_version.desc(),
                GovernanceCopilotDraftSnapshot.created_at.desc(),
                GovernanceCopilotDraftSnapshot.id.desc(),
            )
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Copilot draft snapshot not found")
        return row

    def draft_snapshot_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        by_draft_type_rows = list(
            self.db.execute(
                select(
                    GovernanceCopilotDraftSnapshot.draft_type,
                    func.count(GovernanceCopilotDraftSnapshot.id),
                )
                .where(GovernanceCopilotDraftSnapshot.organization_id == organization_id)
                .group_by(GovernanceCopilotDraftSnapshot.draft_type)
            ).all()
        )
        by_scope_type_rows = list(
            self.db.execute(
                select(
                    GovernanceCopilotDraftSnapshot.scope_type,
                    func.count(GovernanceCopilotDraftSnapshot.id),
                )
                .where(GovernanceCopilotDraftSnapshot.organization_id == organization_id)
                .group_by(GovernanceCopilotDraftSnapshot.scope_type)
            ).all()
        )
        by_draft_type = {str(k): int(v) for k, v in by_draft_type_rows}
        by_scope_type = {str(k): int(v) for k, v in by_scope_type_rows}
        latest_snapshot_at = self.db.execute(
            select(func.max(GovernanceCopilotDraftSnapshot.created_at)).where(
                GovernanceCopilotDraftSnapshot.organization_id == organization_id
            )
        ).scalar_one()
        scopes_with_snapshots = len(
            {
                (str(row[0]), str(row[1]) if row[1] else None)
                for row in self.db.execute(
                    select(
                        GovernanceCopilotDraftSnapshot.scope_type,
                        GovernanceCopilotDraftSnapshot.scope_id,
                    ).where(
                        GovernanceCopilotDraftSnapshot.organization_id == organization_id
                    )
                ).all()
            }
        )
        return {
            "total_snapshots": int(sum(by_draft_type.values())),
            "by_draft_type": by_draft_type,
            "by_scope_type": by_scope_type,
            "latest_snapshot_at": latest_snapshot_at,
            "scopes_with_snapshots": int(scopes_with_snapshots),
            "caveat": GOVERNANCE_COPILOT_DRAFT_SNAPSHOT_CAVEAT,
        }

    def ai_system_copilot_brief(
        self,
        *,
        organization_id: uuid.UUID,
        ai_system_id: uuid.UUID,
    ) -> dict[str, Any]:
        return self._ai_system_attention_brief(
            organization_id=organization_id,
            ai_system_id=ai_system_id,
            include_resolved_signals=False,
        )

    def risk_assessment_copilot_brief(
        self,
        *,
        organization_id: uuid.UUID,
        assessment_id: uuid.UUID,
    ) -> dict[str, Any]:
        assessment = self.risk_service.require_assessment(
            organization_id=organization_id,
            assessment_id=assessment_id,
        )
        return self._risk_assessment_review_brief(
            organization_id=organization_id,
            assessment=assessment,
            include_resolved_signals=False,
        )

    def recommendation_snapshot_copilot_summary(
        self,
        *,
        organization_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        include_dispositions: bool,
    ) -> dict[str, Any]:
        snapshot = self.risk_service.require_recommendation_snapshot(
            organization_id=organization_id,
            snapshot_id=snapshot_id,
        )
        return self._recommendation_snapshot_summary(
            organization_id=organization_id,
            snapshot=snapshot,
            include_dispositions=include_dispositions,
            include_dismissed_recommendations=True,
        )

    def executive_risk_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        return self._executive_risk_summary(organization_id=organization_id)
