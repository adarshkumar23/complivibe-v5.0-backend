"""Normalizes GCP Security Command Center findings delivered via a Pub/Sub push
subscription (https://docs.cloud.google.com/security-command-center/docs/how-to-notifications).
The push envelope is {"message": {"data": "<base64 JSON>", ...}, "subscription": "..."},
where the decoded data is {"finding": {...}, "resource": {...}}.
"""

import base64
import json

from fastapi import HTTPException, status

from app.integrations.cloud_connectors.ingest_pipeline import NormalizedFinding

_SEVERITY_MAP = {
    "CRITICAL": "critical",
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
}

_CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("s3_public_bucket", ["public_bucket", "bucket_acl", "public"]),
    ("iam_overly_broad", ["iam", "overly_broad", "admin_service_account", "primitive_role"]),
    ("encryption_missing", ["encryption", "cmek"]),
    ("network_exposure", ["open_firewall", "firewall", "ssrf"]),
    ("logging_missing", ["logging", "audit_logging"]),
]


def _categorize(category_raw: str) -> str:
    haystack = category_raw.lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return category
    return "other"


def parse_gcp_pubsub_push_payload(envelope: dict) -> NormalizedFinding:
    message = envelope.get("message") or {}
    data_b64 = message.get("data")
    if not data_b64:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Pub/Sub message missing data field")
    try:
        decoded = base64.b64decode(data_b64)
        payload = json.loads(decoded)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to decode Pub/Sub message data") from exc

    finding = payload.get("finding") or payload
    category_raw = str(finding.get("category") or "")
    severity = str(finding.get("severity") or "").upper()

    return NormalizedFinding(
        provider_event_id=str(finding.get("name") or message.get("messageId") or ""),
        category=_categorize(category_raw),
        severity=_SEVERITY_MAP.get(severity, "info"),
        resource_id=finding.get("resourceName"),
        title=f"GCP Security Command Center finding: {category_raw or 'unspecified'}",
        description=str(finding.get("description") or ""),
        raw_payload=finding,
    )
