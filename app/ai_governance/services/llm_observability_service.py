from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_governance.services.ai_governance_event_service import AIGovernanceEventService
from app.models.ai_system import AISystem
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.llm_observability_event import LLMObservabilityEvent
from app.satellites.llm_observability.cost_pricing import UnknownModelPricingError, compute_cost_usd
from app.satellites.llm_observability.langfuse_adapter import LangfuseTraceAdapter
from app.satellites.llm_observability.quality_adapters import DeepEvalHallucinationAdapter, RAGRetrievalQualityAdapter
from app.services.audit_service import AuditService

TRACE_ERROR_RATE_STATIC_THRESHOLD = Decimal("0.05")
RETRIEVAL_RELEVANCE_FLAG_THRESHOLD = Decimal("0.2")
COST_SPIKE_MULTIPLIER = Decimal("1.5")


class LLMObservabilityService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _require_active_ai_system(self, org_id: uuid.UUID, system_id: uuid.UUID) -> AISystem:
        row = self.db.execute(
            select(AISystem).where(
                AISystem.organization_id == org_id,
                AISystem.id == system_id,
                AISystem.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system not found")
        if (
            row.lifecycle_status in {"archived", "decommissioned"}
            or row.deployment_status == "decommissioned"
            or row.archived_at is not None
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="AI system is archived; cannot record new LLM observability events for a retired system",
            )
        return row

    def _recent_values(self, org_id: uuid.UUID, system_id: uuid.UUID, metric_type: str, limit: int = 5) -> list[Decimal]:
        rows = self.db.execute(
            select(LLMObservabilityEvent.value)
            .where(
                LLMObservabilityEvent.organization_id == org_id,
                LLMObservabilityEvent.ai_system_id == system_id,
                LLMObservabilityEvent.metric_type == metric_type,
            )
            .order_by(LLMObservabilityEvent.created_at.desc())
            .limit(limit)
        ).scalars().all()
        return list(rows)

    def _record_event(
        self,
        *,
        org_id: uuid.UUID,
        system_id: uuid.UUID,
        event_type: str,
        source_tool: str,
        metric_type: str,
        value: Decimal,
        is_flagged: bool,
        flag_reason: str | None,
        details: dict,
        actor_id: uuid.UUID | None,
    ) -> LLMObservabilityEvent:
        now = self.utcnow()
        row = LLMObservabilityEvent(
            organization_id=org_id,
            ai_system_id=system_id,
            event_type=event_type,
            source_tool=source_tool,
            metric_type=metric_type,
            value=value,
            is_flagged=is_flagged,
            flag_reason=flag_reason,
            details_json=details,
            created_by=actor_id,
            created_at=now,
        )
        self.db.add(row)
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            f"llm_observability.{event_type}",
            actor_id=actor_id,
            actor_type="user" if actor_id else "system",
            ai_system_id=system_id,
            event_data={"event_id": str(row.id), "metric_type": metric_type, "is_flagged": is_flagged},
        )
        AuditService(self.db).write_audit_log(
            action=f"llm_observability.{event_type}_recorded",
            entity_type="llm_observability_event",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            after_json={
                "ai_system_id": str(system_id),
                "metric_type": metric_type,
                "value": str(value),
                "source_tool": source_tool,
                "is_flagged": is_flagged,
            },
            metadata_json={"source": "llm_observability"},
        )

        if is_flagged:
            alert = ControlMonitoringAlert(
                organization_id=org_id,
                rule_id=None,
                definition_id=None,
                control_id=None,
                alert_type="llm_observability",
                severity="high" if event_type in {"hallucination_check", "cost_reading"} else "medium",
                status="open",
                title=f"LLM observability flag: {metric_type}",
                description=flag_reason or f"{metric_type} flagged for AI system {system_id}",
                alert_context_json={
                    "event_id": str(row.id),
                    "ai_system_id": str(system_id),
                    "event_type": event_type,
                    "metric_type": metric_type,
                    "value": str(value),
                },
            )
            self.db.add(alert)
            self.db.flush()
            AuditService(self.db).write_audit_log(
                action="llm_observability.alert_created",
                entity_type="control_monitoring_alert",
                entity_id=alert.id,
                organization_id=org_id,
                actor_user_id=actor_id,
                after_json={"event_id": str(row.id), "metric_type": metric_type, "severity": alert.severity},
                metadata_json={"source": "llm_observability"},
            )
        return row

    # -- T1-7: Tracing -----------------------------------------------------------------------

    def record_trace_poll(
        self,
        org_id: uuid.UUID,
        system_id: uuid.UUID,
        *,
        public_key: str,
        secret_key: str,
        base_url: str,
        limit: int,
        actor_id: uuid.UUID | None,
    ) -> list[LLMObservabilityEvent]:
        self._require_active_ai_system(org_id, system_id)
        try:
            adapter = LangfuseTraceAdapter(public_key=public_key, secret_key=secret_key, base_url=base_url)
            results = adapter.poll_trace_metrics(limit=limit)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive: never leak a raw traceback
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to poll Langfuse trace metrics: {exc.__class__.__name__}",
            ) from exc

        rows: list[LLMObservabilityEvent] = []
        for result in results:
            is_flagged = False
            flag_reason = None
            if result.metric_type == "langfuse_error_rate":
                history = self._recent_values(org_id, system_id, "langfuse_error_rate")
                baseline = (sum(history) / len(history)) if history else Decimal("0")
                trending_threshold = baseline * COST_SPIKE_MULTIPLIER if baseline > 0 else TRACE_ERROR_RATE_STATIC_THRESHOLD
                if result.value > max(TRACE_ERROR_RATE_STATIC_THRESHOLD, trending_threshold):
                    is_flagged = True
                    flag_reason = (
                        f"Error rate {result.value} exceeds static threshold "
                        f"{TRACE_ERROR_RATE_STATIC_THRESHOLD} and/or 1.5x recent baseline {baseline}"
                    )
            rows.append(
                self._record_event(
                    org_id=org_id,
                    system_id=system_id,
                    event_type="trace",
                    source_tool=result.source_tool,
                    metric_type=result.metric_type,
                    value=result.value,
                    is_flagged=is_flagged,
                    flag_reason=flag_reason,
                    details=result.details,
                    actor_id=actor_id,
                )
            )
        return rows

    # -- T1-8: Hallucination detection --------------------------------------------------------

    def record_hallucination_check(
        self,
        org_id: uuid.UUID,
        system_id: uuid.UUID,
        *,
        prompt: str,
        actual_output: str,
        context: list[str],
        threshold: float,
        actor_id: uuid.UUID | None,
    ) -> LLMObservabilityEvent:
        self._require_active_ai_system(org_id, system_id)
        if not prompt.strip() or not actual_output.strip():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="prompt and actual_output are required")
        if not context:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="context must contain at least one grounding passage")

        try:
            result = DeepEvalHallucinationAdapter().score(
                prompt=prompt, actual_output=actual_output, context=context, threshold=threshold
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Hallucination scoring failed: {exc.__class__.__name__}",
            ) from exc

        is_flagged = not bool(result.details.get("success", True))
        flag_reason = result.details.get("reason") if is_flagged else None
        return self._record_event(
            org_id=org_id,
            system_id=system_id,
            event_type="hallucination_check",
            source_tool=result.source_tool,
            metric_type=result.metric_type,
            value=result.value,
            is_flagged=is_flagged,
            flag_reason=flag_reason,
            details=result.details,
            actor_id=actor_id,
        )

    # -- T1-9: Cost monitoring -----------------------------------------------------------------

    def record_cost_reading(
        self,
        org_id: uuid.UUID,
        system_id: uuid.UUID,
        *,
        model: str,
        input_tokens: int,
        output_tokens: int,
        input_price_per_million: Decimal | None,
        output_price_per_million: Decimal | None,
        actor_id: uuid.UUID | None,
    ) -> LLMObservabilityEvent:
        self._require_active_ai_system(org_id, system_id)
        try:
            cost_usd = compute_cost_usd(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                input_price_per_million=input_price_per_million,
                output_price_per_million=output_price_per_million,
            )
        except UnknownModelPricingError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

        history = self._recent_values(org_id, system_id, "cost_usd", limit=30)
        baseline = (sum(history) / len(history)) if history else Decimal("0")
        is_flagged = bool(baseline > 0 and cost_usd > baseline * COST_SPIKE_MULTIPLIER)
        flag_reason = (
            f"Cost reading ${cost_usd} is more than {COST_SPIKE_MULTIPLIER}x the trailing average ${baseline}"
            if is_flagged
            else None
        )
        return self._record_event(
            org_id=org_id,
            system_id=system_id,
            event_type="cost_reading",
            source_tool="internal_pricing_table",
            metric_type="cost_usd",
            value=cost_usd,
            is_flagged=is_flagged,
            flag_reason=flag_reason,
            details={
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "trailing_average_cost_usd": str(baseline),
            },
            actor_id=actor_id,
        )

    # -- T1-10: RAG monitoring -------------------------------------------------------------------

    def record_rag_evaluation(
        self,
        org_id: uuid.UUID,
        system_id: uuid.UUID,
        *,
        query: str,
        retrieved_contexts: list[str],
        actual_output: str,
        actor_id: uuid.UUID | None,
    ) -> list[LLMObservabilityEvent]:
        self._require_active_ai_system(org_id, system_id)
        if not query.strip():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="query is required")
        if not retrieved_contexts:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="retrieved_contexts must contain at least one chunk")
        if not actual_output.strip():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="actual_output is required")

        try:
            relevance_result = RAGRetrievalQualityAdapter().score_retrieval_relevance(
                query=query, retrieved_contexts=retrieved_contexts
            )
            grounding_result = DeepEvalHallucinationAdapter().score(
                prompt=query, actual_output=actual_output, context=retrieved_contexts, threshold=0.5
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"RAG evaluation failed: {exc.__class__.__name__}",
            ) from exc

        relevance_flagged = relevance_result.value < RETRIEVAL_RELEVANCE_FLAG_THRESHOLD
        grounding_flagged = not bool(grounding_result.details.get("success", True))

        rows = [
            self._record_event(
                org_id=org_id,
                system_id=system_id,
                event_type="rag_evaluation",
                source_tool=relevance_result.source_tool,
                metric_type=relevance_result.metric_type,
                value=relevance_result.value,
                is_flagged=relevance_flagged,
                flag_reason=(
                    f"Retrieved context relevance {relevance_result.value} below threshold {RETRIEVAL_RELEVANCE_FLAG_THRESHOLD}"
                    if relevance_flagged
                    else None
                ),
                details=relevance_result.details,
                actor_id=actor_id,
            ),
            self._record_event(
                org_id=org_id,
                system_id=system_id,
                event_type="rag_evaluation",
                source_tool=grounding_result.source_tool,
                metric_type="rag_groundedness_score",
                value=grounding_result.value,
                is_flagged=grounding_flagged,
                flag_reason=grounding_result.details.get("reason") if grounding_flagged else None,
                details=grounding_result.details,
                actor_id=actor_id,
            ),
        ]
        return rows

    # -- Dashboard -------------------------------------------------------------------------------

    def get_summary(self, org_id: uuid.UUID, system_id: uuid.UUID) -> dict:
        self._require_active_ai_system(org_id, system_id)
        since = self.utcnow() - timedelta(days=30)
        rows = self.db.execute(
            select(LLMObservabilityEvent)
            .where(
                LLMObservabilityEvent.organization_id == org_id,
                LLMObservabilityEvent.ai_system_id == system_id,
                LLMObservabilityEvent.created_at >= since,
            )
            .order_by(LLMObservabilityEvent.created_at.desc())
        ).scalars().all()

        by_type: dict[str, list[LLMObservabilityEvent]] = {}
        for row in rows:
            by_type.setdefault(row.event_type, []).append(row)

        flagged_count = sum(1 for row in rows if row.is_flagged)
        cost_rows = by_type.get("cost_reading", [])
        total_cost_30d = sum((row.value for row in cost_rows), Decimal("0"))

        return {
            "ai_system_id": system_id,
            "window_days": 30,
            "total_events": len(rows),
            "flagged_events": flagged_count,
            "total_cost_usd_30d": total_cost_30d,
            "event_counts_by_type": {key: len(value) for key, value in by_type.items()},
            "recent_events": rows[:20],
        }
