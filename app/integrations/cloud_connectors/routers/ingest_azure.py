import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.integrations.cloud_connectors.connector_service import CloudConnectorService
from app.integrations.cloud_connectors.ingest_pipeline import ingest_normalized_finding
from app.integrations.cloud_connectors.parsers.azure_parser import (
    is_subscription_validation_event,
    parse_azure_event_grid_payload,
)
from app.integrations.cloud_connectors.request_limits import enforce_max_body_size, enforce_max_body_size_from_content_length
from app.integrations.cloud_connectors.signature_verification import verify_shared_secret

router = APIRouter(prefix="/cloud-connectors/ingest/azure", tags=["cloud-evidence-connectors-ingest"])


@router.post("/{webhook_token}")
async def ingest_azure_policy_events(
    webhook_token: str,
    request: Request,
    db: Session = Depends(get_db),
    x_complivibe_shared_secret: str | None = Header(default=None, alias="X-CompliVibe-Shared-Secret"),
) -> dict | list[dict]:
    enforce_max_body_size_from_content_length(request)
    connector_service = CloudConnectorService(db)
    connector = connector_service.get_by_webhook_token("azure", webhook_token)

    raw_body = await request.body()
    enforce_max_body_size(raw_body)
    try:
        events = json.loads(raw_body)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload") from exc
    if not isinstance(events, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payload must be a JSON array of events")

    # Event Grid requires a one-time validation handshake before it starts delivering
    # real events; it does not sign this request, so no secret check applies to it.
    validation_event = is_subscription_validation_event(events)
    if validation_event is not None:
        validation_code = (validation_event.get("data") or {}).get("validationCode")
        return [{"validationResponse": validation_code}]

    secret = connector_service.decrypt_signing_secret(connector)
    if secret is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Connector has no shared secret configured")
    verify_shared_secret(secret=secret, provided_secret=x_complivibe_shared_secret)

    findings = parse_azure_event_grid_payload(events)
    processed = 0
    for finding in findings:
        if not finding.provider_event_id:
            continue
        ingest_normalized_finding(db, connector, finding)
        processed += 1
    db.commit()

    return {"status": "accepted", "findings_processed": processed}
