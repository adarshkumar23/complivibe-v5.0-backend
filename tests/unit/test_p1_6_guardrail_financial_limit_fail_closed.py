"""P1.6 regression: the financial_limit guardrail must FAIL CLOSED. Previously
`action_context.get("estimated_value", 0)` treated a missing/mis-named amount
key as a $0 transaction, so any caller that named the field 'amount' (or omitted
it) silently sailed past every financial limit -- a fail-open security control.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.platform.policy_engine.builtin_engine import BuiltInPolicyEngine


def _guardrail(max_usd=100):
    return SimpleNamespace(guardrail_type="financial_limit", constraint_value={"max_usd": max_usd})


def test_financial_limit_fails_closed_on_missing_or_wrong_key():
    engine = BuiltInPolicyEngine()
    g = _guardrail(100)

    # Correct key, over limit -> block (baseline).
    assert engine.evaluate(g, {"estimated_value": 5000})["decision"] == "block"
    # Correct key, under limit -> permit.
    assert engine.evaluate(g, {"estimated_value": 50})["decision"] == "permit"

    # Wrong-but-plausible key -> must NOT silently permit.
    assert engine.evaluate(g, {"amount": 5000})["decision"] == "block", "wrong key must fail closed"
    # Missing key entirely -> must block.
    assert engine.evaluate(g, {})["decision"] == "block", "missing amount must fail closed"
    # Non-numeric amount -> must block.
    assert engine.evaluate(g, {"estimated_value": "5000"})["decision"] == "block", "non-numeric must fail closed"
    # Boolean is not a valid amount -> must block.
    assert engine.evaluate(g, {"estimated_value": True})["decision"] == "block", "bool must fail closed"
