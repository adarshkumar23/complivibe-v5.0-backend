# mypy: allow-untyped-defs
"""Structural (type-level) trust boundary between what may be transmitted to
CompliVibe's core / OPA for policy evaluation (`ActionEnvelope`) and what must
never leave the customer's own environment (`ActionPayload`).

Per PATENT.md 0/3, this feature only derives and hands off policy; it never
evaluates policy itself and never needs, and must never construct, a network
representation of an `ActionPayload`.

Ported verbatim from P3 `core-side-patch/services/envelope.py`.

Design choices:

* `ActionEnvelope` and `ActionPayload` are two independent `pydantic.BaseModel`
  subclasses with no shared base other than `BaseModel` itself, and no
  overlapping field names. There is no `ActionBase` they both inherit from.
* Both models use `model_config = ConfigDict(extra="forbid")`. Passing a
  payload-only key into `ActionEnvelope(**data)` is a validation error, not a
  value that gets silently dropped.
* `build_envelope()` **rejects** (raises `ValueError`) rather than silently
  stripping payload-shaped keys out of `raw` -- a caller that accidentally
  forwards the whole request should fail loudly at the boundary.
* The reject error path is scrubbed: only field *names* are reported, never
  their values, so logging the exception cannot leak PII/credentials.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

# Field names that only make sense as part of the sensitive payload, and must
# never be accepted into an envelope under any name.
_PAYLOAD_ONLY_FIELDS = frozenset(
    {"raw_request_body", "customer_pii", "documents", "credentials"}
)


class ActionEnvelope(BaseModel):
    """Fields safe to transmit to CompliVibe's core / OPA for policy evaluation.
    Contains only action metadata needed to evaluate policy -- never the
    underlying sensitive request payload.
    """

    model_config = ConfigDict(extra="forbid")

    action_id: str
    ai_system_id: str
    organization_id: str
    action_type: str
    amount: float | None = None
    currency: str | None = None
    destination_region: str | None = None
    data_categories: list[str] = []
    cross_border: bool = False
    requires_approval: bool = False
    approved_by: list[str] = []
    timestamp: str


class ActionPayload(BaseModel):
    """The sensitive material that must stay in the customer's own environment.
    Intentionally shares no base class or field names with `ActionEnvelope`.
    """

    model_config = ConfigDict(extra="forbid")

    raw_request_body: dict = {}
    customer_pii: dict | None = None
    documents: list[dict] = []
    credentials: dict | None = None


def build_envelope(raw: dict) -> ActionEnvelope:
    """Construct an `ActionEnvelope` strictly from the allowed envelope field set.

    If `raw` contains any key that only makes sense as payload (see
    `_PAYLOAD_ONLY_FIELDS`), this function **rejects** the call by raising
    `ValueError` rather than silently stripping those keys and proceeding.

    The raised error message intentionally names only the *offending field
    names*, never their values, so that logging this exception cannot leak
    sensitive payload contents such as PII or credentials.
    """
    offending = sorted(_PAYLOAD_ONLY_FIELDS & raw.keys())
    if offending:
        raise ValueError(
            "build_envelope() received payload-only field(s) "
            f"{offending!r}; payload data must never be passed to "
            "build_envelope() or transmitted to CompliVibe. Extract only "
            "envelope fields at the call site."
        )

    allowed_fields = set(ActionEnvelope.model_fields)
    unexpected = sorted(set(raw.keys()) - allowed_fields)
    if unexpected:
        raise ValueError(
            f"build_envelope() received unrecognized field(s) {unexpected!r}"
        )

    return ActionEnvelope(**raw)
