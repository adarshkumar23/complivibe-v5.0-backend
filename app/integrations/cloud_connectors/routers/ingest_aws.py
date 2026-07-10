import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.integrations.cloud_connectors.connector_service import CloudConnectorService
from app.integrations.cloud_connectors.ingest_pipeline import ingest_normalized_finding
from app.integrations.cloud_connectors.parsers.aws_parser import parse_aws_eventbridge_payload
from app.integrations.cloud_connectors.request_limits import enforce_max_body_size, enforce_max_body_size_from_content_length
from app.integrations.cloud_connectors.signature_verification import verify_hmac_sha256

router = APIRouter(prefix="/cloud-connectors/ingest/aws", tags=["cloud-evidence-connectors-ingest"])


@router.post("/{webhook_token}", status_code=status.HTTP_202_ACCEPTED)
async def ingest_aws_security_hub_finding(
    webhook_token: str,
    request: Request,
    db: Session = Depends(get_db),
    x_complivibe_signature: str | None = Header(default=None, alias="X-CompliVibe-Signature"),
) -> dict:
    enforce_max_body_size_from_content_length(request)
    connector_service = CloudConnectorService(db)
    connector = connector_service.get_by_webhook_token("aws", webhook_token)

    raw_body = await request.body()
    enforce_max_body_size(raw_body)
    secret = connector_service.decrypt_signing_secret(connector)
    if secret is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Connector has no signing secret configured")
    verify_hmac_sha256(secret=secret, raw_body=raw_body, provided_signature=x_complivibe_signature)

    try:
        payload = json.loads(raw_body)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload") from exc

    findings = parse_aws_eventbridge_payload(payload)
    if not findings:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No findings present in payload")

    processed = 0
    for finding in findings:
        if not finding.provider_event_id:
            continue
        ingest_normalized_finding(db, connector, finding)
        processed += 1
    db.commit()

    return {"status": "accepted", "findings_processed": processed}
