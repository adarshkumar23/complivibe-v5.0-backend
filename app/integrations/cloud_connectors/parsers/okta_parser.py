"""Normalizes Okta Event Hooks payloads (https://developer.okta.com/docs/concepts/event-hooks/).
Body shape: {"eventType": "com.okta.event_hook", "data": {"events": [<System Log event>, ...]}}.
Okta System Log events carry Okta's own severity (DEBUG/INFO/WARN/ERROR), not a security
severity scale, so the mapping below is a judgment call, not an Okta-defined equivalence.
"""

from app.integrations.cloud_connectors.ingest_pipeline import NormalizedFinding

_SEVERITY_MAP = {
    "ERROR": "high",
    "WARN": "medium",
    "INFO": "low",
    "DEBUG": "info",
}

_CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("iam_overly_broad", ["privilege", "admin", "role"]),
    ("mfa_change", ["mfa", "factor"]),
    ("policy_change", ["policy"]),
    ("session_anomaly", ["session", "suspicious", "threat"]),
]


def _categorize(event_type: str) -> str:
    haystack = event_type.lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return category
    return "other"


def parse_okta_event_hook_payload(payload: dict) -> list[NormalizedFinding]:
    events = ((payload.get("data") or {}).get("events")) or []
    normalized: list[NormalizedFinding] = []
    for event in events:
        severity_raw = str(event.get("severity") or "INFO").upper()
        targets = event.get("target") or []
        resource_id = targets[0].get("id") if targets else None
        event_type = str(event.get("eventType") or "")
        normalized.append(
            NormalizedFinding(
                provider_event_id=str(event.get("uuid") or ""),
                category=_categorize(event_type),
                severity=_SEVERITY_MAP.get(severity_raw, "info"),
                resource_id=resource_id,
                title=str(event.get("displayMessage") or f"Okta event: {event_type}"),
                description=event_type,
                raw_payload=event,
            )
        )
    return normalized
