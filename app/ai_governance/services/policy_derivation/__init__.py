"""Agentic policy-derivation feature (patent P3).

Automated derivation of machine-enforceable policy (Rego) from regulatory
compliance obligations, with per-obligation provenance, plus the glue needed
to hand the compiled policy to an external agent-action enforcement runtime
(OPA) and store the runtime's cryptographically signed decision receipts
without ever holding the signing key (key-custody boundary, patent Claim 4).

Ported from the standalone `P3-agentic-policy-derivation` repo's
`core-side-patch/`, reconciled to core conventions:
  * `services/receipts.py`'s external `mcp_receipt_governed` dependency is
    replaced by the first-party, dependency-free `receipt_crypto` module
    (Ed25519 over `cryptography`, already a core dependency) -- the signing
    and hash-chaining are prior art (see PATENT.md 1.1(4)), so this does not
    weaken the patent's novel claim (the derivation step).
  * The satellite's in-process `rate_limit` limiter is dropped in favour of
    core's Redis-backed per-org limiter (see app/core/rate_limiter.py).
  * Persistence moves off the in-process dict / SQLite stand-in onto real
    core tables (ai_derived_guardrails, ai_guardrail_check_events,
    ai_guardrail_receipts) via the request-scoped Session.
"""
