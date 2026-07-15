from __future__ import annotations

"""Targeted tests for the Groq model-string fix.

Verifies the Groq chat call uses the env-configurable GROQ_MODEL (default
openai/gpt-oss-120b) instead of the deprecated hardcoded llama-3.3-70b-versatile,
and that the completion budget was raised to leave headroom for reasoning tokens.

No live Groq key is required: httpx.Client.post is stubbed so we assert exactly
what the service would send on the wire.
"""

import httpx

from app.ai_governance.services.ai_provider_service import AIProviderService
from app.core.config import get_settings


class _FakeResp:
    def __init__(self, content: str) -> None:
        self._content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"choices": [{"message": {"content": self._content}}]}


def _capturing_post(captured: dict):
    def _post(self, url, **kwargs):  # noqa: ANN001 - matches httpx.Client.post
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        captured["headers"] = kwargs.get("headers")
        return _FakeResp("DRAFTED TEXT")

    return _post


def test_groq_call_uses_configured_model_and_reasoning_headroom(db_session, monkeypatch):
    get_settings.cache_clear()
    captured: dict = {}
    monkeypatch.setattr(httpx.Client, "post", _capturing_post(captured))

    svc = AIProviderService(db_session)
    out = svc._call_groq_messages(api_key="k", messages=[{"role": "user", "content": "hi"}])

    assert out == "DRAFTED TEXT"
    payload = captured["json"]
    # Deprecated model must be gone; default is the production-tier flagship.
    assert payload["model"] == "openai/gpt-oss-120b"
    assert payload["model"] != "llama-3.3-70b-versatile"
    # Completion budget raised well above the old 1200 to survive reasoning tokens.
    assert payload["max_tokens"] == 8192
    assert payload["max_tokens"] > 1200
    assert captured["url"] == svc.GROQ_URL
    assert captured["headers"]["Authorization"] == "Bearer k"


def test_groq_model_and_max_tokens_are_env_configurable(db_session, monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setenv("GROQ_MAX_TOKENS", "4096")
    get_settings.cache_clear()
    try:
        captured: dict = {}
        monkeypatch.setattr(httpx.Client, "post", _capturing_post(captured))

        svc = AIProviderService(db_session)
        svc._call_groq_messages(api_key="k", messages=[{"role": "user", "content": "hi"}])

        assert captured["json"]["model"] == "openai/gpt-oss-20b"
        assert captured["json"]["max_tokens"] == 4096
    finally:
        get_settings.cache_clear()


def test_no_deprecated_groq_model_string_remains_in_source():
    """Regression guard: the deprecated literal must not reappear in the provider."""
    import inspect

    from app.ai_governance.services import ai_provider_service

    src = inspect.getsource(ai_provider_service)
    # Allowed only inside a comment referencing the removal; assert it's not an
    # active model assignment (i.e. not quoted as a value on a "model" line).
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert "llama-3.3-70b-versatile" not in stripped, (
            f"deprecated Groq model still present in code: {line!r}"
        )
