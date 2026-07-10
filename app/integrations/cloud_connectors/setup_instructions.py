"""Generates the exact, structured configuration a customer needs to wire their own
cloud/IdP provider's native push mechanism at CompliVibe — real, actionable steps (not a
placeholder), sourced from each provider's current documented mechanism. Provider
mechanisms change; re-verify against current docs periodically rather than trusting this
indefinitely.
"""

from app.core.config import get_settings


def _base_webhook_url(connector_type: str, webhook_token: str) -> str:
    settings = get_settings()
    base = getattr(settings, "PUBLIC_API_BASE_URL", None) or "https://api.complivibe.example.com"
    return f"{base}/api/v1/cloud-connectors/ingest/{connector_type}/{webhook_token}"


def build_setup_payload(connector_type: str, webhook_token: str, signing_secret: str | None) -> dict:
    webhook_url = _base_webhook_url(connector_type, webhook_token)

    if connector_type == "aws":
        steps = [
            {
                "title": "Enable AWS Security Hub findings export to EventBridge",
                "description": "Security Hub automatically sends new/updated findings to EventBridge as "
                "'Findings - Imported' events; no separate export step is required beyond enabling Security Hub.",
                "snippet": None,
            },
            {
                "title": "Create an EventBridge rule matching Security Hub findings",
                "description": "Match source aws.securityhub, detail-type 'Security Hub Findings - Imported'.",
                "snippet": (
                    '{"source": ["aws.securityhub"], "detail-type": ["Security Hub Findings - Imported"]}'
                ),
            },
            {
                "title": "Target an EventBridge API Destination pointing at your CompliVibe webhook URL",
                "description": "Create an API Destination + Connection with the signing secret below as a custom "
                "header, then set it as this rule's target. Verify in your account whether API Destinations can "
                "reach this endpoint directly, or whether your organization requires a small Lambda relay instead "
                "(both work; API Destinations avoid needing to write/maintain that Lambda).",
                "snippet": f'Header: X-CompliVibe-Signature: <computed HMAC-SHA256 of the request body using the signing secret>\nURL: {webhook_url}',
            },
        ]
    elif connector_type == "gcp":
        steps = [
            {
                "title": "Enable Security Command Center continuous export to Pub/Sub",
                "description": "Create a notification config exporting SCC findings to a Pub/Sub topic.",
                "snippet": "gcloud scc notifications create complivibe-export --organization=ORG_ID "
                "--pubsub-topic=projects/PROJECT_ID/topics/complivibe-findings --filter=\"state=\\\"ACTIVE\\\"\"",
            },
            {
                "title": "Create an authenticated push subscription to your CompliVibe webhook URL",
                "description": "GCP authenticates push deliveries with a Google-signed OIDC bearer token (not a "
                "shared secret) — provide the service account email in this connector's provider_config_json so "
                "CompliVibe can verify the token's audience and email claims.",
                "snippet": f"gcloud pubsub subscriptions create complivibe-push --topic=complivibe-findings "
                f"--push-endpoint={webhook_url} --push-auth-service-account=SERVICE_ACCOUNT_EMAIL "
                f"--push-auth-token-audience={webhook_url}",
            },
        ]
    elif connector_type == "azure":
        steps = [
            {
                "title": "Create an Event Grid subscription for Azure Policy state change events",
                "description": "Event Grid requires a one-time validation handshake before it delivers real events "
                "— CompliVibe's ingest endpoint handles this automatically on the first request.",
                "snippet": f"az eventgrid event-subscription create --name complivibe-policy-events "
                f"--source-resource-id /subscriptions/SUBSCRIPTION_ID --endpoint-type webhook "
                f"--endpoint {webhook_url}",
            },
            {
                "title": "Add the signing secret as a custom delivery header",
                "description": "Event Grid does not sign payloads by default; CompliVibe verifies ongoing events "
                "via this shared secret in a custom header instead.",
                "snippet": f"--delivery-attribute-mapping X-CompliVibe-Shared-Secret static {signing_secret or '<secret>'} false",
            },
        ]
    elif connector_type == "okta":
        steps = [
            {
                "title": "Create an Event Hook in the Okta Admin Console",
                "description": "Okta will send a one-time verification challenge to the webhook URL, which "
                "CompliVibe's ingest endpoint answers automatically; ongoing events are authenticated via a "
                "static shared-secret header you configure in the same Event Hook setup screen (Okta's own "
                "model — not a computed signature).",
                "snippet": f"Webhook URL: {webhook_url}\nAuthorization header value: {signing_secret or '<secret>'}",
            },
            {
                "title": "Subscribe to the relevant System Log event types",
                "description": "Select the security-relevant event types you want pushed (e.g. policy changes, "
                "MFA factor changes, admin role changes) in the Event Hook's event subscription list.",
                "snippet": None,
            },
        ]
    elif connector_type == "github":
        steps = [
            {
                "title": "Add a webhook to the repository or organization",
                "description": "In Settings > Webhooks, set the Payload URL and Secret; GitHub computes an "
                "HMAC-SHA256 signature over the payload using this secret and sends it in the "
                "X-Hub-Signature-256 header, which CompliVibe verifies.",
                "snippet": f"Payload URL: {webhook_url}\nContent type: application/json\nSecret: {signing_secret or '<secret>'}",
            },
            {
                "title": "Select events",
                "description": "Subscribe to repository security-relevant events: branch protection rule "
                "changes, secret scanning alerts, and repository visibility/settings changes.",
                "snippet": None,
            },
        ]
    else:  # pragma: no cover - guarded by validate_choice at the caller
        steps = []

    return {
        "connector_type": connector_type,
        "webhook_url": webhook_url,
        "signing_secret": signing_secret,
        "provider_setup_steps": steps,
    }
