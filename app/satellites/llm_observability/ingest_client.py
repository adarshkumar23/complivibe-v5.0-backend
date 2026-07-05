from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx

from app.satellites.llm_observability.models import MonitoringIngestTarget, ObservabilityResult


class CoreMonitoringIngestClient:
    """Pushes satellite metric values into core through the confirmed inbound API."""

    INBOUND_PATH = "/api/v1/ai-monitoring/readings"

    def __init__(self, timeout_seconds: float = 10.0) -> None:
        self.timeout_seconds = timeout_seconds

    def push(self, target: MonitoringIngestTarget, result: ObservabilityResult) -> dict[str, Any]:
        if not target.base_url:
            raise ValueError("target.base_url is required")
        if not target.api_key:
            raise ValueError("target.api_key is required")
        if not target.config_id:
            raise ValueError("target.config_id is required")

        payload = {
            "config_id": target.config_id,
            "value": str(result.value),
            "metric_type": target.metric_type or result.metric_type,
            "source_tool": result.source_tool[:100],
        }
        url = target.base_url.rstrip("/") + self.INBOUND_PATH
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(url, headers={"X-CompliVibe-Key": target.api_key}, json=payload)
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Monitoring ingest response must be a JSON object")
        return data

    def push_many(self, target: MonitoringIngestTarget, results: list[ObservabilityResult]) -> list[dict[str, Any]]:
        return [self.push(target, result) for result in results]


def decimal_from_float(value: float) -> Decimal:
    return Decimal(str(round(float(value), 6)))
