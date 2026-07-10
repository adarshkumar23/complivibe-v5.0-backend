"""Normalizes AWS Security Hub findings delivered via an EventBridge 'Findings -
Imported'/'Findings - Updated' event (https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-cwe-event-formats.html).

The EventBridge envelope carries one or more Security Hub finding objects under
detail.findings. Severity.Label is one of INFORMATIONAL/LOW/MEDIUM/HIGH/CRITICAL.
"""

from app.integrations.cloud_connectors.ingest_pipeline import NormalizedFinding

_SEVERITY_MAP = {
    "CRITICAL": "critical",
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
    "INFORMATIONAL": "info",
}

_CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("s3_public_bucket", ["s3", "bucket", "public"]),
    ("iam_overly_broad", ["iam", "policy", "wildcard", "overly permissive", "*:*"]),
    ("encryption_missing", ["encryption", "unencrypted", "kms"]),
    ("network_exposure", ["security group", "0.0.0.0/0", "ingress", "port"]),
    ("logging_missing", ["cloudtrail", "logging", "log group"]),
]


def _categorize(finding: dict) -> str:
    haystack = " ".join(
        filter(
            None,
            [
                finding.get("Title", ""),
                " ".join(finding.get("Types") or []),
                finding.get("GeneratorId", ""),
            ],
        )
    ).lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return category
    return "other"


def parse_aws_eventbridge_payload(payload: dict) -> list[NormalizedFinding]:
    findings = (payload.get("detail") or {}).get("findings")
    if findings is None:
        # Some setups (Lambda relay) may unwrap to a single finding at the top level.
        findings = [payload["detail"]] if "detail" in payload else [payload]

    normalized: list[NormalizedFinding] = []
    for finding in findings:
        severity_label = ((finding.get("Severity") or {}).get("Label") or "INFORMATIONAL").upper()
        resources = finding.get("Resources") or []
        resource_id = resources[0].get("Id") if resources else None
        normalized.append(
            NormalizedFinding(
                provider_event_id=str(finding.get("Id") or finding.get("GeneratorId") or ""),
                category=_categorize(finding),
                severity=_SEVERITY_MAP.get(severity_label, "info"),
                resource_id=resource_id,
                title=str(finding.get("Title") or "AWS Security Hub finding"),
                description=str(finding.get("Description") or ""),
                raw_payload=finding,
            )
        )
    return normalized
