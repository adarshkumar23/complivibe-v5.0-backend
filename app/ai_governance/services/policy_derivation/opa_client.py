# mypy: allow-untyped-defs
"""Thin HTTP client for an already-running, separately-deployed OPA instance.

Deploying, clustering, or operating OPA is out of scope for this feature; this
module only calls an OPA HTTP API assumed to already be up. Ported verbatim
from P3 `core-side-patch/services/opa_client.py` (observability import made
package-relative to the no-op metrics shim).

Fail-closed by design: if OPA cannot be reached, times out, returns a non-2xx
status, or returns an unparseable response, `evaluate()` returns
`allowed=False, source="fail_closed"` -- an OPA outage becomes a
deny-everything incident rather than a silent policy bypass.
"""

from __future__ import annotations

import concurrent.futures
import time
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from .metrics import OPA_CIRCUIT_BREAKER_TRANSITIONS

__all__ = ["OpaDecision", "OpaClient"]


@dataclass(frozen=True)
class OpaDecision:
    allowed: bool
    raw_result: Any
    source: Literal["opa", "fail_closed"]
    error: str | None
    evaluation_ms: float


class OpaClient:
    """Synchronous HTTP client for OPA's `POST /v1/data/<path>` decision API.

    Fail-closed by design. Only connection-level failures (connect errors,
    timeouts) are retried; a clean non-2xx is a real answer and is not retried.
    A circuit breaker skips the HTTP attempt entirely after
    `circuit_breaker_threshold` consecutive failures until cooldown elapses.
    """

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 2.0,
        max_retries: int = 2,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_cooldown_seconds: float = 30.0,
        client: httpx.Client | None = None,
        backoff_base_seconds: float = 0.05,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.circuit_breaker_threshold = circuit_breaker_threshold
        self.circuit_breaker_cooldown_seconds = circuit_breaker_cooldown_seconds
        self.backoff_base_seconds = backoff_base_seconds

        self._client = client or httpx.Client(timeout=timeout_seconds)

        self._consecutive_failures = 0
        self._circuit_open_until: float | None = None

    def _circuit_is_open(self) -> bool:
        if self._circuit_open_until is None:
            return False
        if time.monotonic() >= self._circuit_open_until:
            self._circuit_open_until = None
            self._consecutive_failures = 0
            OPA_CIRCUIT_BREAKER_TRANSITIONS.labels(transition="closed").inc()
            return False
        return True

    def _record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.circuit_breaker_threshold:
            was_open = self._circuit_open_until is not None
            self._circuit_open_until = (
                time.monotonic() + self.circuit_breaker_cooldown_seconds
            )
            if not was_open:
                OPA_CIRCUIT_BREAKER_TRANSITIONS.labels(transition="opened").inc()

    def _record_success(self) -> None:
        self._consecutive_failures = 0
        self._circuit_open_until = None

    def _post_with_timeout(self, url: str, input_data: dict) -> httpx.Response:
        """Issue the OPA POST with a timeout enforced independently of the
        underlying transport (bounds slow-but-successful transports too).
        """
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self._client.post, url, json={"input": input_data})
        try:
            return future.result(timeout=self.timeout_seconds)
        except concurrent.futures.TimeoutError:
            raise httpx.ReadTimeout(
                f"OPA call exceeded timeout_seconds={self.timeout_seconds}s "
                "(enforced independently of the underlying transport)"
            )
        finally:
            executor.shutdown(wait=False)

    def evaluate(
        self,
        package: str | None = None,
        input_data: dict | None = None,
        *,
        query_path: str | None = None,
    ) -> OpaDecision:
        """Ask OPA to evaluate a policy against `input_data`."""
        input_data = input_data or {}
        if query_path is not None:
            path = query_path.strip("/")
        elif package is not None:
            path = package.replace(".", "/").strip("/") + "/allow"
        else:
            raise ValueError("evaluate() requires either `package` or `query_path`")

        url = f"{self.base_url}/v1/data/{path}"
        started = time.monotonic()

        if self._circuit_is_open():
            return OpaDecision(
                allowed=False,
                raw_result=None,
                source="fail_closed",
                error=(
                    "circuit breaker open: too many consecutive OPA failures; "
                    "skipping HTTP call during cooldown"
                ),
                evaluation_ms=(time.monotonic() - started) * 1000.0,
            )

        last_error: str | None = None
        attempts = self.max_retries + 1

        for attempt in range(attempts):
            try:
                response = self._post_with_timeout(url, input_data)
            except (httpx.ConnectError, httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < attempts - 1:
                    time.sleep(self.backoff_base_seconds * (2**attempt))
                    continue
                self._record_failure()
                return OpaDecision(
                    allowed=False,
                    raw_result=None,
                    source="fail_closed",
                    error=last_error,
                    evaluation_ms=(time.monotonic() - started) * 1000.0,
                )

            if response.status_code < 200 or response.status_code >= 300:
                self._record_failure()
                return OpaDecision(
                    allowed=False,
                    raw_result=None,
                    source="fail_closed",
                    error=(
                        f"OPA returned non-2xx status {response.status_code}: "
                        f"{response.text[:500]!r}"
                    ),
                    evaluation_ms=(time.monotonic() - started) * 1000.0,
                )

            try:
                body = response.json()
            except ValueError as exc:
                self._record_failure()
                return OpaDecision(
                    allowed=False,
                    raw_result=None,
                    source="fail_closed",
                    error=f"malformed JSON from OPA: {exc}",
                    evaluation_ms=(time.monotonic() - started) * 1000.0,
                )

            if not isinstance(body, dict) or "result" not in body:
                self._record_failure()
                return OpaDecision(
                    allowed=False,
                    raw_result=None,
                    source="fail_closed",
                    error=f"OPA response missing 'result' key: {body!r}",
                    evaluation_ms=(time.monotonic() - started) * 1000.0,
                )

            result = body["result"]
            self._record_success()
            return OpaDecision(
                allowed=bool(result),
                raw_result=result,
                source="opa",
                error=None,
                evaluation_ms=(time.monotonic() - started) * 1000.0,
            )

        self._record_failure()
        return OpaDecision(
            allowed=False,
            raw_result=None,
            source="fail_closed",
            error=last_error or "unknown failure evaluating OPA policy",
            evaluation_ms=(time.monotonic() - started) * 1000.0,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "OpaClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
