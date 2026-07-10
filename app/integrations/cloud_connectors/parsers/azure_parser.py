"""Normalizes Azure Policy compliance state change events delivered via Event Grid
(Event Grid schema, not CloudEvents — a JSON array of events per delivery).
https://learn.microsoft.com/en-us/azure/governance/policy/concepts/event-overview

NOTE: unlike AWS/GCP findings, Azure Policy compliance events carry no severity or
human-readable finding category out of the box (just complianceState and policy/resource
IDs) — categorization here is a coarse heuristic on the policy assignment/definition id
string. A real deployment would want to resolve the policy definition's display name via
the customer's own tooling and include it in the event, since CompliVibe cannot call out
to Azure to look it up (agent-push only).
"""

from app.integrations.cloud_connectors.ingest_pipeline import NormalizedFinding

SUBSCRIPTION_VALIDATION_EVENT_TYPE = "Microsoft.EventGrid.SubscriptionValidationEvent"
POLICY_STATE_EVENT_TYPES = {
    "Microsoft.PolicyInsights.PolicyStateCreated",
    "Microsoft.PolicyInsights.PolicyStateChanged",
}

_CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("encryption_missing", ["encrypt"]),
    ("network_exposure", ["network", "firewall", "publicip", "nsg"]),
    ("s3_public_bucket", ["storageaccount", "blob", "public"]),
    ("logging_missing", ["diagnosticsetting", "logging", "auditing"]),
]


def is_subscription_validation_event(events: list[dict]) -> dict | None:
    for event in events:
        if event.get("eventType") == SUBSCRIPTION_VALIDATION_EVENT_TYPE:
            return event
    return None


def _categorize(policy_definition_id: str, policy_assignment_id: str) -> str:
    haystack = f"{policy_definition_id} {policy_assignment_id}".lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return category
    return "other"


def parse_azure_event_grid_payload(events: list[dict]) -> list[NormalizedFinding]:
    normalized: list[NormalizedFinding] = []
    for event in events:
        if event.get("eventType") not in POLICY_STATE_EVENT_TYPES:
            continue
        data = event.get("data") or {}
        compliance_state = str(data.get("complianceState") or "").lower()
        policy_definition_id = str(data.get("policyDefinitionId") or "")
        policy_assignment_id = str(data.get("policyAssignmentId") or "")
        resource_id = data.get("resourceId") or event.get("subject")

        severity = "high" if compliance_state == "noncompliant" else "info"
        normalized.append(
            NormalizedFinding(
                provider_event_id=str(event.get("id") or ""),
                category=_categorize(policy_definition_id, policy_assignment_id),
                severity=severity,
                resource_id=resource_id,
                title=f"Azure Policy compliance state: {compliance_state or 'unknown'} for {resource_id}",
                description=f"Policy assignment {policy_assignment_id} evaluated resource {resource_id} as {compliance_state}.",
                raw_payload=event,
            )
        )
    return normalized
