"""AI assessment of uploaded evidence — the narrate step of the evidence-vault
AI-assist, built on the existing Groq->Azure provider chain (no new AI dep).

Placed in its own module (rather than as a method on AIProviderService) so this
feature does NOT touch ai_provider_service.py, which carries a separate pending
Azure-fallback commit. It reuses the committed, shared ``_run_provider_chain``
so it gets the exact same Groq-primary / Azure-fallback behavior.

Discipline mirrors Phase 3's compound narrative: strict json_schema output, and
the function RAISES on any failure (no key, timeout, chain 502, malformed) so the
drain records ``unable_to_assess`` -- an evidence item is never blocked by an
AI-layer problem. The model is framed to ASSESS, never to certify.
"""

from __future__ import annotations

import json
import uuid

from sqlalchemy.orm import Session

from app.ai_governance.services.ai_provider_service import AIProviderService
from app.models.evidence_ai_assessment import ASSESSMENT_STATUSES

# Strict json_schema: all properties required + additionalProperties:false + an
# enum-constrained status. Confirmed supported by Groq structured outputs
# (strict + enum + additionalProperties:false), same contract as the shipped
# COMPOUND_NARRATIVE_SCHEMA.
EVIDENCE_ASSESSMENT_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "evidence_ai_assessment",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "ai_assessment_status": {"type": "string", "enum": list(ASSESSMENT_STATUSES)},
                "appears_to_be": {"type": "string"},
                "appears_to_cover": {"type": "string"},
                "missing_or_mismatched": {"type": "array", "items": {"type": "string"}},
                "explanation": {"type": "string"},
            },
            "required": [
                "ai_assessment_status",
                "appears_to_be",
                "appears_to_cover",
                "missing_or_mismatched",
                "explanation",
            ],
            "additionalProperties": False,
        },
    },
}

_SYSTEM_PROMPT = (
    "You are ASSESSING compliance evidence for a human reviewer -- you are NOT certifying it. "
    "You must NEVER state that the evidence is correct, verified, valid, compliant, or approved as a "
    "fact; you only offer a SUGGESTION with reasoning. Choose ai_assessment_status from exactly these: "
    "'suggested_valid' (the document appears to support what it is linked to), 'suggested_incomplete' "
    "(content is partial, unclear, or key information is missing), 'suggested_mismatch' (the document "
    "appears to contradict or not correspond to the linked control/obligation), 'unable_to_assess' "
    "(there is not enough readable content to judge). If little or no document text is available, prefer "
    "'suggested_incomplete' or 'unable_to_assess'. 'appears_to_be' = what the document seems to be; "
    "'appears_to_cover' = what it seems to address; 'missing_or_mismatched' = concrete gaps relative to "
    "the linked control. Do not invent facts beyond the provided payload."
)


def generate_evidence_assessment(db: Session, *, org_id: uuid.UUID, payload: dict) -> tuple[dict, str, bool]:
    """Best-effort AI assessment. Returns (assessment_dict, provider_used, used_byo).

    Raises on any failure so the caller records ``unable_to_assess``.
    """
    provider = AIProviderService(db)
    user = (
        "Assess this uploaded compliance evidence. Return ONLY the structured assessment.\n\n"
        + json.dumps(payload, default=str, ensure_ascii=False)
    )
    messages = [{"role": "system", "content": _SYSTEM_PROMPT}, {"role": "user", "content": user}]

    # Reuse the shared, committed Groq->Azure chain (no edits to ai_provider_service.py).
    text, provider_used, byo = provider._run_provider_chain(
        org_id=org_id,
        messages=messages,
        failure_context="Evidence AI assessment unavailable",
        response_format=EVIDENCE_ASSESSMENT_SCHEMA,
    )

    parsed = json.loads(text)  # raises on malformed -> caller falls back
    status = str(parsed.get("ai_assessment_status") or "").strip()
    if status not in ASSESSMENT_STATUSES:
        raise RuntimeError(f"Evidence assessment returned invalid status: {status!r}")
    explanation = str(parsed.get("explanation") or "").strip()
    if not explanation:
        raise RuntimeError("Evidence assessment missing explanation")

    missing_raw = parsed.get("missing_or_mismatched") or []
    if not isinstance(missing_raw, list):
        raise RuntimeError("Evidence assessment missing_or_mismatched is not a list")
    missing = [str(m).strip()[:300] for m in missing_raw if str(m).strip()][:20]

    return (
        {
            "ai_assessment_status": status,
            "appears_to_be": str(parsed.get("appears_to_be") or "").strip()[:1000] or None,
            "appears_to_cover": str(parsed.get("appears_to_cover") or "").strip()[:1000] or None,
            "missing_or_mismatched": missing,
            "explanation": explanation[:4000],
        },
        provider_used,
        byo,
    )
