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


def test_deepeval_hallucination_adapter_scores_sample_case():
    from app.satellites.llm_observability.quality_adapters import DeepEvalHallucinationAdapter

    result = DeepEvalHallucinationAdapter().score(
        prompt="Where is Paris?",
        actual_output="Paris is in France.",
        context=["Paris is the capital of France."],
    )

    assert result.metric_type == "hallucination_score"
    assert result.source_tool == "deepeval"
    assert result.value == Decimal("0.0")
    assert result.details["success"] is True


def test_giskard_scan_adapter_runs_real_scan_on_sample_data():
    from app.satellites.llm_observability.quality_adapters import (
        GiskardScanAdapter,
        build_sample_giskard_dataframe,
        sample_giskard_predict_proba,
    )

    data = build_sample_giskard_dataframe()
    result = GiskardScanAdapter().scan_classification(
        dataframe=data,
        target="label",
        prediction_function=sample_giskard_predict_proba,
        feature_names=["text", "group"],
        classification_labels=[0, 1],
        detectors="performance",
        cat_columns=["group"],
    )

    assert result.metric_type == "giskard_issue_count"
    assert result.source_tool == "giskard"
    assert result.value >= 0
    assert result.details["detectors"] == "performance"


def test_aif360_fairness_adapter_computes_formal_metrics():
    from app.satellites.llm_observability.fairness_adapters import AIF360FairnessAdapter, build_sample_fairness_dataframe

    results = AIF360FairnessAdapter().assess_binary_classification(
        dataframe=build_sample_fairness_dataframe(),
        label_column="label",
        prediction_column="prediction",
        protected_attribute="protected",
        privileged_value=1,
        unprivileged_value=0,
    )

    metrics = {result.metric_type: result.value for result in results}
    assert metrics["aif360_mean_difference"] == Decimal("-0.5")
    assert metrics["aif360_disparate_impact"] == Decimal("0.333333")
    assert metrics["aif360_equal_opportunity_difference"] == Decimal("0.333333")


def test_fairlearn_monitoring_adapter_computes_lightweight_metrics():
    from app.satellites.llm_observability.fairness_adapters import FairlearnMonitoringAdapter, build_sample_fairness_dataframe

    data = build_sample_fairness_dataframe()
    results = FairlearnMonitoringAdapter().assess_binary_classification(
        y_true=data["label"].tolist(),
        y_pred=data["prediction"].tolist(),
        sensitive_features=data["protected"].tolist(),
    )

    metrics = {result.metric_type: result.value for result in results}
    assert metrics["fairlearn_demographic_parity_difference"] == Decimal("0.0")
    assert metrics["fairlearn_equalized_odds_difference"] == Decimal("0.333333")
