import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.integrations.cloud_connectors.connector_service import CloudConnectorService
from app.integrations.cloud_connectors.finding_mapping_service import FindingControlMappingService
from app.integrations.cloud_connectors.schemas import (
    ConnectorCreate,
    ConnectorCreateResponse,
    ConnectorHealthRead,
    ConnectorRead,
    ConnectorSetupRead,
    DismissSuggestionRequest,
    FindingSuggestionRead,
)
from app.integrations.cloud_connectors.setup_instructions import build_setup_payload
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/cloud-connectors", tags=["cloud-evidence-connectors"])


@router.post("", response_model=ConnectorCreateResponse, status_code=status.HTTP_201_CREATED)
def create_connector(
    payload: ConnectorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("connectors:write")),
) -> ConnectorCreateResponse:
    row, plaintext_secret = CloudConnectorService(db).create_connector(
        organization.id,
        payload.connector_type,
        payload.display_name,
        payload.provider_config_json,
        current_user.id,
    )
    db.commit()
    db.refresh(row)
    return ConnectorCreateResponse(connector=ConnectorRead.model_validate(row), signing_secret=plaintext_secret)


@router.get("", response_model=list[ConnectorRead])
def list_connectors(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("connectors:read")),
) -> list[ConnectorRead]:
    rows = CloudConnectorService(db).list_connectors(organization.id)
    return [ConnectorRead.model_validate(row) for row in rows]


@router.get("/{connector_id}", response_model=ConnectorRead)
def get_connector(
    connector_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("connectors:read")),
) -> ConnectorRead:
    row = CloudConnectorService(db).get_connector(organization.id, connector_id)
    return ConnectorRead.model_validate(row)


@router.get("/{connector_id}/health", response_model=ConnectorHealthRead)
def get_connector_health(
    connector_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("connectors:read")),
) -> ConnectorHealthRead:
    return ConnectorHealthRead(**CloudConnectorService(db).health(organization.id, connector_id))


@router.get("/{connector_id}/setup", response_model=ConnectorSetupRead)
def get_connector_setup(
    connector_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("connectors:read")),
) -> ConnectorSetupRead:
    service = CloudConnectorService(db)
    connector = service.get_connector(organization.id, connector_id)
    # Signing secret is only ever revealed in the create response; setup always redacts it.
    payload = build_setup_payload(connector.connector_type, connector.webhook_token, signing_secret=None)
    return ConnectorSetupRead(**payload)


@router.post("/{connector_id}/activate", response_model=ConnectorRead)
def activate_connector(
    connector_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("connectors:write")),
) -> ConnectorRead:
    row = CloudConnectorService(db).activate_connector(organization.id, connector_id, current_user.id)
    db.commit()
    db.refresh(row)
    return ConnectorRead.model_validate(row)


@router.post("/{connector_id}/disable", response_model=ConnectorRead)
def disable_connector(
    connector_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("connectors:write")),
) -> ConnectorRead:
    row = CloudConnectorService(db).disable_connector(organization.id, connector_id, current_user.id)
    db.commit()
    db.refresh(row)
    return ConnectorRead.model_validate(row)


@router.post("/suggestions/{suggestion_id}/apply", response_model=FindingSuggestionRead)
def apply_finding_suggestion(
    suggestion_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("evidence:write")),
) -> FindingSuggestionRead:
    row = FindingControlMappingService(db).apply_suggestion(organization.id, suggestion_id, current_user.id)
    db.commit()
    db.refresh(row)
    return FindingSuggestionRead.model_validate(row)


@router.post("/suggestions/{suggestion_id}/dismiss", response_model=FindingSuggestionRead)
def dismiss_finding_suggestion(
    suggestion_id: uuid.UUID,
    payload: DismissSuggestionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("evidence:write")),
) -> FindingSuggestionRead:
    row = FindingControlMappingService(db).dismiss_suggestion(organization.id, suggestion_id, payload.reason, current_user.id)
    db.commit()
    db.refresh(row)
    return FindingSuggestionRead.model_validate(row)
