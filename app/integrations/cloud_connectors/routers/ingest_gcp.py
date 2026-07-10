from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.integrations.cloud_connectors.connector_service import CloudConnectorService
from app.integrations.cloud_connectors.ingest_pipeline import ingest_normalized_finding
from app.integrations.cloud_connectors.parsers.gcp_parser import parse_gcp_pubsub_push_payload
from app.integrations.cloud_connectors.signature_verification import verify_gcp_oidc_bearer_token

router = APIRouter(prefix="/cloud-connectors/ingest/gcp", tags=["cloud-evidence-connectors-ingest"])


@router.post("/{webhook_token}", status_code=status.HTTP_202_ACCEPTED)
def ingest_gcp_scc_finding(
    webhook_token: str,
    envelope: dict,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> dict:
    connector_service = CloudConnectorService(db)
    connector = connector_service.get_by_webhook_token("gcp", webhook_token)

    expected_audience = connector.provider_config_json.get("push_audience") or connector.webhook_token
    expected_service_account = connector.provider_config_json.get("service_account_email")
    if not expected_service_account:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Connector is missing provider_config_json.service_account_email required for OIDC verification",
        )
    verify_gcp_oidc_bearer_token(
        authorization_header=authorization,
        expected_audience=expected_audience,
        expected_service_account_email=expected_service_account,
    )

    finding = parse_gcp_pubsub_push_payload(envelope)
    if not finding.provider_event_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Finding missing a stable identifier")

    ingest_normalized_finding(db, connector, finding)
    db.commit()

    return {"status": "accepted", "findings_processed": 1}
