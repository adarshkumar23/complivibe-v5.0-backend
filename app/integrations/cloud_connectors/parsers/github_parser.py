"""Normalizes GitHub webhook deliveries for repository security settings, branch
protection, and secret scanning alerts (https://docs.github.com/en/webhooks/webhook-events-and-payloads).
GitHub sends one event per delivery, identified by the X-GitHub-Delivery header (used as
the dedup key here, since these payloads don't always carry their own stable id)."""

from fastapi import HTTPException, status

from app.integrations.cloud_connectors.ingest_pipeline import NormalizedFinding

SUPPORTED_EVENT_TYPES = {"secret_scanning_alert", "branch_protection_rule", "repository"}


def parse_github_webhook_payload(event_type: str, delivery_id: str, payload: dict) -> NormalizedFinding | None:
    if event_type not in SUPPORTED_EVENT_TYPES:
        return None

    repo_full_name = (payload.get("repository") or {}).get("full_name", "unknown-repo")
    action = str(payload.get("action") or "")

    if event_type == "secret_scanning_alert":
        alert = payload.get("alert") or {}
        secret_type = alert.get("secret_type_display_name") or alert.get("secret_type") or "secret"
        return NormalizedFinding(
            provider_event_id=delivery_id,
            category="secret_scanning",
            severity="critical" if action in {"created", "reopened"} else "medium",
            resource_id=repo_full_name,
            title=f"Secret scanning alert ({action}): {secret_type} detected in {repo_full_name}",
            description=f"GitHub secret scanning alert #{alert.get('number')} for {repo_full_name}: state={alert.get('state')}",
            raw_payload=payload,
        )

    if event_type == "branch_protection_rule":
        rule = payload.get("rule") or {}
        severity = "high" if action == "deleted" else "medium"
        return NormalizedFinding(
            provider_event_id=delivery_id,
            category="branch_protection",
            severity=severity,
            resource_id=repo_full_name,
            title=f"Branch protection rule {action} on {repo_full_name}",
            description=f"Branch protection rule for pattern '{rule.get('pattern_name') or rule.get('name')}' was {action}.",
            raw_payload=payload,
        )

    # event_type == "repository": we only care about visibility/security-relevant changes.
    if action not in {"publicized", "privatized"}:
        return None
    return NormalizedFinding(
        provider_event_id=delivery_id,
        category="repo_visibility_change",
        severity="high" if action == "publicized" else "info",
        resource_id=repo_full_name,
        title=f"Repository {repo_full_name} visibility changed: {action}",
        description=f"Repository {repo_full_name} was {action}.",
        raw_payload=payload,
    )


def require_event_type(event_type: str | None) -> str:
    if not event_type:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing X-GitHub-Event header")
    return event_type
