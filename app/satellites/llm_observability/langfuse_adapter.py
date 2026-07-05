from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from langfuse import Langfuse

from app.satellites.llm_observability.ingest_client import decimal_from_float
from app.satellites.llm_observability.models import ObservabilityResult


def _to_plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    if hasattr(value, "__dict__"):
        return {key: _to_plain(val) for key, val in value.__dict__.items() if not key.startswith("_")}
    return value


class LangfuseTraceAdapter:
    """Polls Langfuse traces using the installed Langfuse 4.x generated API client."""

    def __init__(self, *, public_key: str, secret_key: str, base_url: str, environment: str | None = None) -> None:
        if not public_key or not secret_key or not base_url:
            raise ValueError("public_key, secret_key, and base_url are required for Langfuse polling")
        self.client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            base_url=base_url,
            environment=environment,
            tracing_enabled=False,
        )

    def poll_trace_metrics(
        self,
        *,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
        limit: int = 50,
        environment: str | None = None,
    ) -> list[ObservabilityResult]:
        traces_response = self.client.api.trace.list(
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp or datetime.now(timezone.utc),
            limit=limit,
            environment=environment,
        )
        payload = _to_plain(traces_response)
        traces = payload.get("data") or payload.get("traces") or []
        if not isinstance(traces, list):
            traces = []

        error_count = 0
        latency_values: list[float] = []
        for trace in traces:
            if not isinstance(trace, dict):
                continue
            level = str(trace.get("level") or trace.get("status") or "").lower()
            if level in {"error", "warning"} or trace.get("error"):
                error_count += 1
            latency = trace.get("latency") or trace.get("duration") or trace.get("durationMs")
            if isinstance(latency, (int, float)):
                latency_values.append(float(latency))

        trace_count = len(traces)
        error_rate = (error_count / trace_count) if trace_count else 0.0
        avg_latency = (sum(latency_values) / len(latency_values)) if latency_values else 0.0
        details = {"trace_count": trace_count, "error_count": error_count, "limit": limit}
        return [
            ObservabilityResult("langfuse_trace_count", Decimal(trace_count), "langfuse", details),
            ObservabilityResult("langfuse_error_rate", decimal_from_float(error_rate), "langfuse", details),
            ObservabilityResult("langfuse_avg_latency", decimal_from_float(avg_latency), "langfuse", details),
        ]

    def poll_generation_spans(
        self,
        *,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Returns real per-call LLM spans (one row per generation): model, prompt/completion
        token counts, and latency -- the actual per-call tracing data, as opposed to
        poll_trace_metrics' trace-level aggregates.
        """
        response = self.client.api.observations.get_many(
            type="GENERATION",
            fields="core,basic,usage,model,metrics",
            from_start_time=from_timestamp,
            to_start_time=to_timestamp or datetime.now(timezone.utc),
            limit=limit,
        )
        payload = _to_plain(response)
        observations = payload.get("data") or []
        if not isinstance(observations, list):
            observations = []

        spans: list[dict[str, Any]] = []
        for obs in observations:
            if not isinstance(obs, dict):
                continue
            usage = obs.get("usageDetails") or obs.get("usage") or {}
            input_tokens = usage.get("input") or usage.get("promptTokens") or 0
            output_tokens = usage.get("output") or usage.get("completionTokens") or 0
            spans.append(
                {
                    "observation_id": obs.get("id"),
                    "trace_id": obs.get("traceId"),
                    "model": obs.get("providedModelName") or obs.get("model"),
                    "input_tokens": int(input_tokens or 0),
                    "output_tokens": int(output_tokens or 0),
                    "latency_ms": float(obs.get("latency") or 0.0),
                    "name": obs.get("name"),
                }
            )
        return spans
