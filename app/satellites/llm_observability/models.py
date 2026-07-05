from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class ObservabilityResult:
    metric_type: str
    value: Decimal
    source_tool: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MonitoringIngestTarget:
    base_url: str
    api_key: str
    config_id: str
    metric_type: str | None = None
