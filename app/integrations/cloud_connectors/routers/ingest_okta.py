import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.integrations.cloud_connectors.connector_service import CloudConnectorService
from app.integrations.cloud_connectors.ingest_pipeline import ingest_normalized_finding
from app.integrations.cloud_connectors.parsers.okta_parser import parse_okta_event_hook_payload
from app.integrations.cloud_connectors.request_limits import enforce_max_body_size, enforce_max_body_size_from_content_length
from app.integrations.cloud_connectors.signature_verification import verify_shared_secret

router = APIRouter(prefix="/cloud-connectors/ingest/okta", tags=["cloud-evidence-connectors-ingest"])


@router.get("/{webhook_token}")
def verify_okta_event_hook(
    webhook_token: str,
    db: Session = Depends(get_db),
    x_okta_verification_challenge: str | None = Header(default=None, alias="x-okta-verification-challenge"),
) -> dict:
    """Okta's one-time Event Hook verification handshake: echo the challenge value back
    in a {"verification": ...} JSON body. https://developer.okta.com/docs/concepts/event-hooks/"""
    CloudConnectorService(db).get_by_webhook_token("okta", webhook_token)
    if not x_okta_verification_challenge:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing x-okta-verification-challenge header")
    return {"verification": x_okta_verification_challenge}


@router.post("/{webhook_token}", status_code=status.HTTP_202_ACCEPTED)
async def ingest_okta_event_hook(
    webhook_token: str,
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> dict:
    enforce_max_body_size_from_content_length(request)
    connector_service = CloudConnectorService(db)
    connector = connector_service.get_by_webhook_token("okta", webhook_token)

    secret = connector_service.decrypt_signing_secret(connector)
    if secret is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Connector has no shared secret configured")
    # Okta's own model: a static shared value in a configured header (here, Authorization),
    # not a computed signature.
    verify_shared_secret(secret=secret, provided_secret=authorization)

    raw_body = await request.body()
    enforce_max_body_size(raw_body)
    try:
        payload = json.loads(raw_body)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payload must be a JSON object")

    findings = parse_okta_event_hook_payload(payload)
    processed = 0
    for finding in findings:
        if not finding.provider_event_id:
            continue
        ingest_normalized_finding(db, connector, finding)
        processed += 1
    db.commit()

    return {"status": "accepted", "findings_processed": processed}
