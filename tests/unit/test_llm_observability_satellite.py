from __future__ import annotations

from decimal import Decimal

from app.satellites.llm_observability.ingest_client import CoreMonitoringIngestClient
from app.satellites.llm_observability.models import MonitoringIngestTarget, ObservabilityResult


def test_core_monitoring_ingest_client_uses_confirmed_inbound_contract(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "reading-1"}

    class FakeHttpClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, headers, json):
            captured.update({"url": url, "headers": headers, "json": json})
            return FakeResponse()

    monkeypatch.setattr("app.satellites.llm_observability.ingest_client.httpx.Client", FakeHttpClient)
    result = CoreMonitoringIngestClient(timeout_seconds=3).push(
        MonitoringIngestTarget(
            base_url="https://core.example.test/",
            api_key="inbound-key-123456",
            config_id="11111111-1111-1111-1111-111111111111",
            metric_type="hallucination_score",
        ),
        ObservabilityResult("hallucination_score", Decimal("0.25"), "deepeval"),
    )

    assert result == {"id": "reading-1"}
    assert captured["url"] == "https://core.example.test/api/v1/ai-monitoring/readings"
    assert captured["headers"] == {"X-CompliVibe-Key": "inbound-key-123456"}
    assert captured["json"] == {
        "config_id": "11111111-1111-1111-1111-111111111111",
        "value": "0.25",
        "metric_type": "hallucination_score",
        "source_tool": "deepeval",
    }


def test_langfuse_trace_adapter_converts_trace_list(monkeypatch):
    from app.satellites.llm_observability import langfuse_adapter

    class FakeTraceApi:
        def list(self, **kwargs):
            return {
                "data": [
                    {"id": "t1", "level": "DEFAULT", "latency": 10},
                    {"id": "t2", "level": "ERROR", "latency": 30},
                ]
            }

    class FakeApi:
        trace = FakeTraceApi()

    class FakeLangfuse:
        def __init__(self, **kwargs):
            self.api = FakeApi()

    monkeypatch.setattr(langfuse_adapter, "Langfuse", FakeLangfuse)
    adapter = langfuse_adapter.LangfuseTraceAdapter(public_key="pk", secret_key="sk", base_url="https://langfuse.example")

    results = adapter.poll_trace_metrics(limit=2)

    assert [(r.metric_type, r.value, r.source_tool) for r in results] == [
        ("langfuse_trace_count", Decimal("2"), "langfuse"),
        ("langfuse_error_rate", Decimal("0.5"), "langfuse"),
        ("langfuse_avg_latency", Decimal("20.0"), "langfuse"),
    ]
