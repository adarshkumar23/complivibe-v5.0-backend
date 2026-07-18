from __future__ import annotations

"""Targeted tests for the Azure fallback leg's Responses-API migration.

Verifies the Azure call uses client.responses.create (NOT chat.completions),
passes the env-configurable model (deployment name) and AZURE_OPENAI_MAX_TOKENS,
sends the messages as `input`, omits `temperature` (gpt-5.1 is a reasoning
model), translates a Chat-Completions json_schema response_format into the
Responses `text.format` shape, and reads back `output_text`.

No live Azure key required: the OpenAI client is stubbed.
"""

from types import SimpleNamespace

from app.ai_governance.services import ai_provider_service
from app.ai_governance.services.ai_provider_service import AIProviderService
from app.core.config import Settings, get_settings


class _FakeResponses:
    def __init__(self, captured: dict) -> None:
        self._c = captured

    def create(self, **kwargs):  # matches client.responses.create
        self._c.update(kwargs)
        # Return valid JSON when structured output requested, else plain text.
        text = (
            '{"headline": "h", "summary": "s", "recommended_actions": ["a"]}'
            if kwargs.get("text")
            else "AZURE DRAFT"
        )
        return SimpleNamespace(output_text=text, status="completed")


def _fake_openai_factory(captured: dict):
    def _factory(**init_kwargs):
        captured["client_init"] = init_kwargs
        return SimpleNamespace(responses=_FakeResponses(captured))

    return _factory


def test_azure_leg_uses_responses_api_with_configured_model_and_budget(db_session, monkeypatch):
    get_settings.cache_clear()
    captured: dict = {}
    monkeypatch.setattr(ai_provider_service, "OpenAI", _fake_openai_factory(captured))

    svc = AIProviderService(db_session)
    out = svc._call_azure_messages(
        api_key="k",
        endpoint="https://res.services.ai.azure.com/openai/v1",
        deployment_name="gpt-5.1",
        messages=[{"role": "user", "content": "hi"}],
    )

    assert out == "AZURE DRAFT"
    # API-key auth via the OpenAI SDK pointed at the Azure v1 base.
    assert captured["client_init"]["api_key"] == "k"
    assert captured["client_init"]["base_url"] == "https://res.services.ai.azure.com/openai/v1"
    # Responses-API shape: model + input, reasoning-friendly budget, no temperature.
    assert captured["model"] == "gpt-5.1"
    assert captured["input"] == [{"role": "user", "content": "hi"}]
    assert captured["max_output_tokens"] == get_settings().AZURE_OPENAI_MAX_TOKENS
    assert "temperature" not in captured
    assert "text" not in captured  # no structured output requested here
    # Code default budget is generous for reasoning tokens.
    assert Settings.model_fields["AZURE_OPENAI_MAX_TOKENS"].default == 8192


def test_azure_leg_translates_response_format_to_responses_text_format(db_session, monkeypatch):
    get_settings.cache_clear()
    captured: dict = {}
    monkeypatch.setattr(ai_provider_service, "OpenAI", _fake_openai_factory(captured))

    svc = AIProviderService(db_session)
    out = svc._call_azure_messages(
        api_key="k",
        endpoint="https://res.services.ai.azure.com/openai/v1",
        deployment_name="gpt-5.1",
        messages=[{"role": "user", "content": "hi"}],
        response_format=AIProviderService.COMPOUND_NARRATIVE_SCHEMA,
    )

    assert out == '{"headline": "h", "summary": "s", "recommended_actions": ["a"]}'
    fmt = captured["text"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["name"] == "compound_insight_narrative"
    assert fmt["strict"] is True
    # The nested schema object is carried over intact.
    assert fmt["schema"] == AIProviderService.COMPOUND_NARRATIVE_SCHEMA["json_schema"]["schema"]


def test_azure_model_and_budget_are_env_configurable(db_session, monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_MAX_TOKENS", "4096")
    get_settings.cache_clear()
    try:
        captured: dict = {}
        monkeypatch.setattr(ai_provider_service, "OpenAI", _fake_openai_factory(captured))
        svc = AIProviderService(db_session)
        svc._call_azure_messages(
            api_key="k",
            endpoint="https://res.services.ai.azure.com/openai/v1",
            deployment_name="gpt-4o",  # model is not hardcoded — flows from the arg
            messages=[{"role": "user", "content": "hi"}],
        )
        assert captured["model"] == "gpt-4o"
        assert captured["max_output_tokens"] == 4096
    finally:
        get_settings.cache_clear()
