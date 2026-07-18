"""Dependency-free metric shims.

The standalone P3 repo used `prometheus_client` Counters/Histograms in its
`observability.py`. Core does not depend on `prometheus_client`, so rather
than add a new dependency for a handful of counters, this module provides
tiny no-op stand-ins exposing the same `.labels(**kw).inc()` / `.observe()`
surface the ported `opa_client`, `policy_provider`, and router code call.

If core later adopts a real metrics backend, swap these objects for the real
Counter/Histogram instances without touching any call site.
"""

from __future__ import annotations


class _NoopMetric:
    """Exposes `.labels(...).inc()` and `.observe(...)` as no-ops."""

    def labels(self, *args: object, **kwargs: object) -> "_NoopMetric":
        return self

    def inc(self, amount: float = 1.0) -> None:  # noqa: D401 - trivial
        return None

    def observe(self, amount: float) -> None:
        return None


# Names mirror the ported code's expectations exactly.
OPA_CIRCUIT_BREAKER_TRANSITIONS = _NoopMetric()
REGO_COMPILATION_RESULTS = _NoopMetric()
CHECK_ACTION_DECISIONS = _NoopMetric()
CHECK_ACTION_LATENCY = _NoopMetric()
CHAIN_VERIFICATION_RESULTS = _NoopMetric()
