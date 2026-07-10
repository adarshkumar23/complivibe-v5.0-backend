import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.integrations.cloud_connectors.connector_service import CloudConnectorService
from app.integrations.cloud_connectors.ingest_pipeline import ingest_normalized_finding
from app.integrations.cloud_connectors.parsers.github_parser import parse_github_webhook_payload, require_event_type
from app.integrations.cloud_connectors.signature_verification import verify_hmac_sha256

router = APIRouter(prefix="/cloud-connectors/ingest/github", tags=["cloud-evidence-connectors-ingest"])


@router.post("/{webhook_token}", status_code=status.HTTP_202_ACCEPTED)
async def ingest_github_webhook(
    webhook_token: str,
    request: Request,
    db: Session = Depends(get_db),
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
    x_github_event: str | None = Header(default=None, alias="X-GitHub-Event"),
    x_github_delivery: str | None = Header(default=None, alias="X-GitHub-Delivery"),
) -> dict:
    connector_service = CloudConnectorService(db)
    connector = connector_service.get_by_webhook_token("github", webhook_token)

    raw_body = await request.body()
    secret = connector_service.decrypt_signing_secret(connector)
    if secret is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Connector has no signing secret configured")
    verify_hmac_sha256(secret=secret, raw_body=raw_body, provided_signature=x_hub_signature_256)

    event_type = require_event_type(x_github_event)
    if not x_github_delivery:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing X-GitHub-Delivery header")

    try:
        payload = json.loads(raw_body)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload") from exc

    finding = parse_github_webhook_payload(event_type, x_github_delivery, payload)
    if finding is None:
        return {"status": "ignored", "reason": f"event_type '{event_type}' not actionable"}

    ingest_normalized_finding(db, connector, finding)
    db.commit()

    return {"status": "accepted", "findings_processed": 1}
