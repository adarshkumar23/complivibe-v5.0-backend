from __future__ import annotations

from tests.helpers.auth_org import bootstrap_org_user

SYSTEMS_BASE = "/api/v1/ai-governance/systems"
LLM_OBS_BASE = "/api/v1/ai-governance/llm-observability"


def _create_system(client, headers: dict[str, str], owner_id: str, name: str) -> str:
    resp = client.post(
        SYSTEMS_BASE,
        headers=headers,
        json={
            "name": name,
            "system_type": "model",
            "owner_id": owner_id,
            "deployment_status": "development",
            "risk_tier": "limited",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_hallucination_check_happy_path_and_edge_cases(client):
    org = bootstrap_org_user(client, email_prefix="llmobs-halluc")
    system_id = _create_system(client, org["org_headers"], org["user_id"], "Halluc System")

    # Happy path: grounded answer -> not flagged
    resp = client.post(
        f"{LLM_OBS_BASE}/systems/{system_id}/hallucination-checks",
        headers=org["org_headers"],
        json={
            "prompt": "Where is Paris?",
            "actual_output": "Paris is in France.",
            "context": ["Paris is the capital of France."],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["metric_type"] == "hallucination_score"
    assert body["source_tool"] == "deepeval"
    assert body["is_flagged"] is False

    # Edge case: forcing the deterministic judge's contradiction path -> flagged + alert
    resp2 = client.post(
        f"{LLM_OBS_BASE}/systems/{system_id}/hallucination-checks",
        headers=org["org_headers"],
        json={
            "prompt": "What does the policy say?",
            "actual_output": "force_local_contradiction: this claim is unsupported by context.",
            "context": ["Unrelated grounding text."],
        },
    )
    assert resp2.status_code == 201, resp2.text
    assert resp2.json()["is_flagged"] is True

    alerts = client.get(
        "/api/v1/compliance/monitoring/alerts?alert_type=llm_observability", headers=org["org_headers"]
    )
    assert alerts.status_code == 200
    assert any(a["title"].startswith("LLM observability flag: hallucination_score") for a in alerts.json())

    # Edge case: empty context -> specific 422, not a 500
    bad = client.post(
        f"{LLM_OBS_BASE}/systems/{system_id}/hallucination-checks",
        headers=org["org_headers"],
        json={"prompt": "x", "actual_output": "y", "context": []},
    )
    assert bad.status_code == 422
    assert "context" in str(bad.json()["detail"])

    # Edge case: unknown system id -> 404, not 500
    missing = client.post(
        f"{LLM_OBS_BASE}/systems/00000000-0000-0000-0000-000000000000/hallucination-checks",
        headers=org["org_headers"],
        json={"prompt": "x", "actual_output": "y", "context": ["z"]},
    )
    assert missing.status_code == 404


def test_cost_reading_computes_real_dollar_cost_and_flags_spikes(client):
    org = bootstrap_org_user(client, email_prefix="llmobs-cost")
    system_id = _create_system(client, org["org_headers"], org["user_id"], "Cost System")

    resp = client.post(
        f"{LLM_OBS_BASE}/systems/{system_id}/cost-readings",
        headers=org["org_headers"],
        json={"model": "gpt-4o-mini", "input_tokens": 1_000_000, "output_tokens": 1_000_000},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # gpt-4o-mini: $0.15 input + $0.60 output per 1M tokens => $0.75 total
    assert body["value"] == "0.750000"
    assert body["metric_type"] == "cost_usd"
    assert body["is_flagged"] is False

    # Unknown model without explicit price override -> specific 422
    unknown = client.post(
        f"{LLM_OBS_BASE}/systems/{system_id}/cost-readings",
        headers=org["org_headers"],
        json={"model": "not-a-real-model", "input_tokens": 100, "output_tokens": 100},
    )
    assert unknown.status_code == 422
    assert "not-a-real-model" in unknown.json()["detail"]

    # Unknown model WITH explicit override prices -> succeeds
    override = client.post(
        f"{LLM_OBS_BASE}/systems/{system_id}/cost-readings",
        headers=org["org_headers"],
        json={
            "model": "custom-enterprise-model",
            "input_tokens": 1_000_000,
            "output_tokens": 0,
            "input_price_per_million": "3.00",
            "output_price_per_million": "9.00",
        },
    )
    assert override.status_code == 201, override.text
    assert override.json()["value"] == "3.000000"

    # Build a cost-spike baseline: several small readings, then a 10x spike should flag
    for _ in range(5):
        client.post(
            f"{LLM_OBS_BASE}/systems/{system_id}/cost-readings",
            headers=org["org_headers"],
            json={"model": "gpt-4o-mini", "input_tokens": 10_000, "output_tokens": 10_000},
        )
    spike = client.post(
        f"{LLM_OBS_BASE}/systems/{system_id}/cost-readings",
        headers=org["org_headers"],
        json={"model": "gpt-5.5", "input_tokens": 1_000_000, "output_tokens": 1_000_000},
    )
    assert spike.status_code == 201, spike.text
    assert spike.json()["is_flagged"] is True

    # Negative tokens are a malformed input -> 422 not 500
    negative = client.post(
        f"{LLM_OBS_BASE}/systems/{system_id}/cost-readings",
        headers=org["org_headers"],
        json={"model": "gpt-4o", "input_tokens": -5, "output_tokens": 10},
    )
    assert negative.status_code == 422


def test_rag_evaluation_flags_low_relevance_retrieval(client):
    org = bootstrap_org_user(client, email_prefix="llmobs-rag")
    system_id = _create_system(client, org["org_headers"], org["user_id"], "RAG System")

    good = client.post(
        f"{LLM_OBS_BASE}/systems/{system_id}/rag-evaluations",
        headers=org["org_headers"],
        json={
            "query": "What is our data retention policy for customer records?",
            "retrieved_contexts": [
                "Our data retention policy for customer records requires deletion after 7 years."
            ],
            "actual_output": "Customer records are retained for 7 years per policy.",
        },
    )
    assert good.status_code == 201, good.text
    metric_types = {row["metric_type"] for row in good.json()}
    assert metric_types == {"retrieval_relevance_score", "rag_groundedness_score"}
    assert all(row["is_flagged"] is False for row in good.json())

    poor = client.post(
        f"{LLM_OBS_BASE}/systems/{system_id}/rag-evaluations",
        headers=org["org_headers"],
        json={
            "query": "What is our data retention policy for customer records?",
            "retrieved_contexts": ["The cafeteria menu changes every Tuesday."],
            "actual_output": "I don't know.",
        },
    )
    assert poor.status_code == 201, poor.text
    relevance_row = next(r for r in poor.json() if r["metric_type"] == "retrieval_relevance_score")
    assert relevance_row["is_flagged"] is True

    # Malformed: empty retrieved_contexts list -> 422
    bad = client.post(
        f"{LLM_OBS_BASE}/systems/{system_id}/rag-evaluations",
        headers=org["org_headers"],
        json={"query": "x", "retrieved_contexts": [], "actual_output": "y"},
    )
    assert bad.status_code == 422


def test_trace_poll_records_events_from_langfuse(client, monkeypatch):
    from app.satellites.llm_observability import langfuse_adapter

    class FakeTraceApi:
        def list(self, **kwargs):
            return {
                "data": [
                    {"id": "t1", "level": "DEFAULT", "latency": 100},
                    {"id": "t2", "level": "ERROR", "latency": 900},
                ]
            }

    class FakeApi:
        trace = FakeTraceApi()

    class FakeLangfuse:
        def __init__(self, **kwargs):
            self.api = FakeApi()

    monkeypatch.setattr(langfuse_adapter, "Langfuse", FakeLangfuse)

    org = bootstrap_org_user(client, email_prefix="llmobs-trace")
    system_id = _create_system(client, org["org_headers"], org["user_id"], "Trace System")

    resp = client.post(
        f"{LLM_OBS_BASE}/systems/{system_id}/trace-polls",
        headers=org["org_headers"],
        json={"public_key": "pk", "secret_key": "sk", "base_url": "https://langfuse.example", "limit": 10},
    )
    assert resp.status_code == 201, resp.text
    metric_types = {row["metric_type"] for row in resp.json()}
    assert metric_types == {"langfuse_trace_count", "langfuse_error_rate", "langfuse_avg_latency"}
    error_rate_row = next(r for r in resp.json() if r["metric_type"] == "langfuse_error_rate")
    assert error_rate_row["value"] == "0.500000"
    # 50% error rate exceeds the 5% static threshold -> flagged
    assert error_rate_row["is_flagged"] is True

    summary = client.get(f"{LLM_OBS_BASE}/systems/{system_id}/summary", headers=org["org_headers"])
    assert summary.status_code == 200, summary.text
    summary_body = summary.json()
    assert summary_body["total_events"] == 3
    assert summary_body["flagged_events"] == 1


def test_permission_gate_and_archived_system_are_rejected(client):
    org = bootstrap_org_user(client, email_prefix="llmobs-perm")
    system_id = _create_system(client, org["org_headers"], org["user_id"], "Perm System")

    # `client` carries a session cookie set by an earlier register() call -- clear it to
    # actually test the fully-unauthenticated case.
    client.cookies.clear()
    no_auth_headers = {"X-Organization-ID": org["organization_id"]}
    resp = client.post(
        f"{LLM_OBS_BASE}/systems/{system_id}/cost-readings",
        headers=no_auth_headers,
        json={"model": "gpt-4o", "input_tokens": 100, "output_tokens": 100},
    )
    assert resp.status_code == 401

    retire = client.post(
        f"{SYSTEMS_BASE}/{system_id}/status",
        headers=org["org_headers"],
        json={"new_status": "decommissioned"},
    )
    assert retire.status_code == 200, retire.text

    retired = client.post(
        f"{LLM_OBS_BASE}/systems/{system_id}/cost-readings",
        headers=org["org_headers"],
        json={"model": "gpt-4o", "input_tokens": 100, "output_tokens": 100},
    )
    assert retired.status_code == 422
    assert "retired system" in retired.json()["detail"]
